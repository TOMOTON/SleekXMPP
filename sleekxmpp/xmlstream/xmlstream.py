"""
    SleekXMPP: The Sleek XMPP Library
    Copyright (C) 2010  Nathanael C. Fritz
    This file is part of SleekXMPP.

    See the file LICENSE for copying permission.
"""

from __future__ import with_statement, unicode_literals
try:
	import queue
except ImportError:
	import Queue as queue
from . import statemachine
from . stanzabase import StanzaBase
from xml.etree import cElementTree
from xml.parsers import expat
import logging
import socket
import threading
import time
import types
import copy
import xml.sax.saxutils
from . import scheduler
from sleekxmpp.xmlstream.tostring import tostring

RESPONSE_TIMEOUT = 10
HANDLER_THREADS = 1

ssl_support = True
#try:
import ssl
#except ImportError:
#	ssl_support = False
import sys
if sys.version_info < (3, 0):
	#monkey patch broken filesocket object
	from . import filesocket
	#socket._fileobject = filesocket.filesocket


class RestartStream(Exception):
	pass

class CloseStream(Exception):
	pass

stanza_extensions = {}

class XMLStream(object):
	"A connection manager with XML events."

	def __init__(self, socket=None, host='', port=0, escape_quotes=False):
		global ssl_support
		self.ssl_support = ssl_support
		self.escape_quotes = escape_quotes
		self.state = statemachine.StateMachine()
		self.state.addStates({'connected':False, 'is client':False, 'ssl':False, 'tls':False, 'reconnect':True, 'processing':False, 'disconnecting':False}) #set initial states

		self.setSocket(socket)
		self.address = (host, int(port))

		self.__thread = {}

		self.__root_stanza = []
		self.__stanza = {}
		self.__stanza_extension = {}
		self.__handlers = []

		self.__tls_socket = None
		self.filesocket = None
		self.use_ssl = False
		self.use_tls = False

		self.default_ns = ''
		self.stream_header = "<stream>"
		self.stream_footer = "</stream>"

		self.eventqueue = queue.Queue()
		self.sendqueue = queue.Queue()
		self.scheduler = scheduler.Scheduler(self.eventqueue)

		self.namespace_map = {}

		self.run = True

	def setSocket(self, socket):
		"Set the socket"
		self.socket = socket
		if socket is not None:
			self.filesocket = socket.makefile('rb', 0) # ElementTree.iterparse requires a file.  0 buffer files have to be binary
			self.state.set('connected', True)


	def setFileSocket(self, filesocket):
		self.filesocket = filesocket

	def connect(self, host='', port=0, use_ssl=False, use_tls=True):
		"Link to connectTCP"
		return self.connectTCP(host, port, use_ssl, use_tls)

	def connectTCP(self, host='', port=0, use_ssl=None, use_tls=None, reattempt=True):
		"Connect and create socket"
		while reattempt and not self.state['connected']:
			if host and port:
				self.address = (host, int(port))
			if use_ssl is not None:
				self.use_ssl = use_ssl
			if use_tls is not None:
				self.use_tls = use_tls
			self.state.set('is client', True)
			if sys.version_info < (3, 0):
				self.socket = filesocket.Socket26(socket.AF_INET, socket.SOCK_STREAM)
			else:
				self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.socket.settimeout(None)
			if self.use_ssl and self.ssl_support:
				logging.debug("Socket Wrapped for SSL")
				self.socket = ssl.wrap_socket(self.socket)
			try:
				self.socket.connect(self.address)
				#self.filesocket = self.socket.makefile('rb', 0)
				self.filesocket = self.socket.makefile('rb', 0)
				self.state.set('connected', True)
				return True
			except socket.error as serr:
				logging.error("Could not connect. Socket Error #%s: %s" % (serr.errno, serr.strerror))
				time.sleep(1)

	def connectUnix(self, filepath):
		"Connect to Unix file and create socket"

	def startTLS(self):
		"Handshakes for TLS"
		if self.ssl_support:
			logging.info("Negotiating TLS")
			self.realsocket = self.socket
			self.socket = ssl.wrap_socket(self.socket, ssl_version=ssl.PROTOCOL_TLSv1, do_handshake_on_connect=False)
			self.socket.do_handshake()
			if sys.version_info < (3,0):
				self.filesocket = filesocket.FileSocket(self.socket)
			else:
				self.filesocket = self.socket.makefile('rb', 0)
			return True
		else:
			logging.warning("Tried to enable TLS, but ssl module not found.")
			return False
		raise RestartStream()

	def process(self, threaded=True):
		self.scheduler.process(threaded=True)
		for t in range(0, HANDLER_THREADS):
			logging.debug("Starting HANDLER THREAD")
			self.__thread['eventhandle%s' % t] = threading.Thread(name='eventhandle%s' % t, target=self._eventRunner)
			self.__thread['eventhandle%s' % t].start()
		self.__thread['sendthread'] = threading.Thread(name='sendthread', target=self._sendThread)
		self.__thread['sendthread'].start()
		if threaded:
			self.__thread['process'] = threading.Thread(name='process', target=self._process)
			self.__thread['process'].start()
		else:
			self._process()

	def schedule(self, name, seconds, callback, args=None, kwargs=None, repeat=False):
		self.scheduler.add(name, seconds, callback, args, kwargs, repeat, qpointer=self.eventqueue)

	def _process(self):
		"Start processing the socket."
		firstrun = True
		while self.run and (firstrun or self.state['reconnect']):
			self.state.set('processing', True)
			firstrun = False
			try:
				if self.state['is client']:
					self.sendRaw(self.stream_header)
				while self.run and self.__readXML():
					if self.state['is client']:
						self.sendRaw(self.stream_header)
			except KeyboardInterrupt:
				logging.debug("Keyboard Escape Detected")
				self.state.set('processing', False)
				self.state.set('reconnect', False)
				self.disconnect()
				self.run = False
				self.scheduler.run = False
				self.eventqueue.put(('quit', None, None))
				return
			except CloseStream:
				return
			except SystemExit:
				self.eventqueue.put(('quit', None, None))
				return
			except socket.error:
				if not self.state.reconnect:
					return
				else:
					self.state.set('processing', False)
					logging.exception('Socket Error')
					self.disconnect(reconnect=True)
			except:
				if not self.state.reconnect:
					return
				else:
					self.state.set('processing', False)
					logging.exception('Connection error. Reconnecting.')
					self.disconnect(reconnect=True)
			if self.state['reconnect']:
				self.reconnect()
			self.state.set('processing', False)
			self.eventqueue.put(('quit', None, None))
		#self.__thread['readXML'] = threading.Thread(name='readXML', target=self.__readXML)
		#self.__thread['readXML'].start()
		#self.__thread['spawnEvents'] = threading.Thread(name='spawnEvents', target=self.__spawnEvents)
		#self.__thread['spawnEvents'].start()

	def __readXML(self):
		"Parses the incoming stream, adding to xmlin queue as it goes"
		#build cElementTree object from expat was we go
		#self.filesocket = self.socket.makefile('rb', 0)
		#print self.filesocket.read(1024) #self.filesocket._sock.recv(1024)
		edepth = 0
		root = None
		for (event, xmlobj) in cElementTree.iterparse(self.filesocket, (b'end', b'start')):
			if edepth == 0: # and xmlobj.tag.split('}', 1)[-1] == self.basetag:
				if event == b'start':
					root = xmlobj
					self.start_stream_handler(root)
			if event == b'end':
				edepth += -1
				if edepth == 0 and event == b'end':
					self.disconnect(reconnect=self.state['reconnect'])
					logging.debug("Ending readXML loop")
					return False
				elif edepth == 1:
					#self.xmlin.put(xmlobj)
					try:
						self.__spawnEvent(xmlobj)
					except RestartStream:
						return True
					except CloseStream:
						logging.debug("Ending readXML loop")
						return False
					if root:
						root.clear()
			if event == b'start':
				edepth += 1
		logging.debug("Ending readXML loop")

	def _sendThread(self):
		while self.run:
			data = self.sendqueue.get(True)
			logging.debug("SEND: %s" % data)
			try:
				self.socket.send(data.encode('utf-8'))
				#self.socket.send(bytes(data, "utf-8"))
				#except socket.error,(errno, strerror):
			except:
				logging.warning("Failed to send %s" % data)
				self.state.set('connected', False)
				if self.state.reconnect:
					logging.exception("Disconnected. Socket Error.")
					self.disconnect(reconnect=True)

	def sendRaw(self, data):
		self.sendqueue.put(data)
		return True

	def disconnect(self, reconnect=False):
		self.state.set('reconnect', reconnect)
		if self.state['disconnecting']:
			return
		if not self.state['reconnect']:
			logging.debug("Disconnecting...")
			self.state.set('disconnecting', True)
			self.run = False
			self.scheduler.run = False
		if self.state['connected']:
			self.sendRaw(self.stream_footer)
			time.sleep(1)
			#send end of stream
			#wait for end of stream back
		try:
			self.socket.close()
			self.filesocket.close()
			self.socket.shutdown(socket.SHUT_RDWR)
		except socket.error as serr:
			#logging.warning("Error while disconnecting. Socket Error #%s: %s" % (errno, strerror))
			#thread.exit_thread()
			pass
		if self.state['processing']:
			#raise CloseStream
			pass

	def reconnect(self):
		self.state.set('tls',False)
		self.state.set('ssl',False)
		time.sleep(1)
		self.connect()

	def incoming_filter(self, xmlobj):
		return xmlobj

	def __spawnEvent(self, xmlobj):
		"watching xmlOut and processes handlers"
		#convert XML into Stanza
		logging.debug("RECV: %s" % tostring(xmlobj, xmlns=self.default_ns, stream=self))
		xmlobj = self.incoming_filter(xmlobj)
		stanza_type = StanzaBase
		for stanza_class in self.__root_stanza:
			if xmlobj.tag == "{%s}%s" % (self.default_ns, stanza_class.name):
				stanza_type = stanza_class
				break
		unhandled = True
		stanza = stanza_type(self, xmlobj)
		for handler in self.__handlers:
			if handler.match(stanza):
				stanza_copy = stanza_type(self, copy.deepcopy(xmlobj))
				handler.prerun(stanza_copy)
				self.eventqueue.put(('stanza', handler, stanza_copy))
				try:
					if handler.checkDelete(): self.__handlers.pop(self.__handlers.index(handler))
				except ValueError:
					pass # could not delete handler
				unhandled = False
		if unhandled:
			stanza.unhandled()
			#loop through handlers and test match
			#spawn threads as necessary, call handlers, sending Stanza

	def _eventRunner(self):
		logging.debug("Loading event runner")
		while self.run:
			try:
				event = self.eventqueue.get(True, timeout=5)
			except queue.Empty:
				event = None
			except KeyboardInterrupt:
				self.run = False
				self.scheduler.run = False
			if event is not None:
				etype = event[0]
				handler = event[1]
				args = event[2:]
				#etype, handler, *args = event  #python 3.x way
				if etype == 'stanza':
					try:
						handler.run(args[0])
					except Exception as e:
						logging.exception('Error processing event handler: %s' % handler.name)
						args[0].exception(e)
				elif etype == 'schedule':
					try:
						logging.debug(args)
						handler(*args[0])
					except:
						logging.exception('Error processing scheduled task')
				elif etype == 'quit':
					logging.debug("Quitting eventRunner thread")
					return False

	def registerHandler(self, handler, before=None, after=None):
 		"Add handler with matcher class and parameters."
 		if handler.stream is None:
 			self.__handlers.append(handler)
 			handler.stream = self

	def removeHandler(self, name):
		"Removes the handler."
		idx = 0
		for handler in self.__handlers:
			if handler.name == name:
				self.__handlers.pop(idx)
				return True
			idx += 1
		return False


	def registerStanza(self, stanza_class):
		"Adds stanza.  If root stanzas build stanzas sent in events while non-root stanzas build substanza objects."
		self.__root_stanza.append(stanza_class)

	def registerStanzaExtension(self, stanza_class, stanza_extension):
		if stanza_class not in stanza_extensions:
			stanza_extensions[stanza_class] = [stanza_extension]
		else:
			stanza_extensions[stanza_class].append(stanza_extension)

	def removeStanza(self, stanza_class, root=False):
		"Removes the stanza's registration."
		if root:
			del self.__root_stanza[stanza_class]
		else:
			del self.__stanza[stanza_class]

	def removeStanzaExtension(self, stanza_class, stanza_extension):
		stanza_extension[stanza_class].pop(stanza_extension)

	def start_stream_handler(self, xml):
		"""Meant to be overridden"""
		pass
