"""
    SleekXMPP: The Sleek XMPP Library
    Copyright (C) 2010 Nathanael C. Fritz
    This file is part of SleekXMPP.
    
    See the file LICENSE for copying permission.
"""
from xml.etree import cElementTree as ET
from . import base
import time
import logging

class xep_0199(base.base_plugin):
	"""XEP-0199 XMPP Ping"""

	def plugin_init(self):
		self.description = "XMPP Ping"
		self.xep = "0199"
		self.xmpp.add_handler("<iq type='get' xmlns='%s'><ping xmlns='http://www.xmpp.org/extensions/xep-0199.html#ns'/></iq>" % self.xmpp.default_ns, self.handler_ping, name='XMPP Ping')
		self.running = False
		#if self.config.get('keepalive', True):
			#self.xmpp.add_event_handler('session_start', self.handler_pingserver, threaded=True)
	
	def post_init(self):
		base.base_plugin.post_init(self)
		self.xmpp.plugin['xep_0030'].add_feature('http://www.xmpp.org/extensions/xep-0199.html#ns')
	
	def handler_pingserver(self, xml):
		if not self.running:
			time.sleep(self.config.get('frequency', 300))
			while self.sendPing(self.xmpp.domain, self.config.get('timeout', 30)) is not False:
				time.sleep(self.config.get('frequency', 300))
			logging.debug("Did not recieve ping back in time.  Requesting Reconnect.")
			self.xmpp.disconnect(reconnect=True)
	
	def handler_ping(self, xml):
		iq = self.xmpp.makeIqResult(xml.get('id', 'unknown'))
		iq.attrib['to'] = xml.get('from', self.xmpp.domain)
		self.xmpp.send(iq)

	def sendPing(self, jid, timeout = 30):
		""" sendPing(jid, timeout)
		Sends a ping to the specified jid, returning the time (in seconds)
		to receive a reply, or None if no reply is received in timeout seconds.
		"""
		iq = self.xmpp.makeIqGet()
		iq.attrib['to'] = jid
		ping = ET.Element('{http://www.xmpp.org/extensions/xep-0199.html#ns}ping')
		iq.append(ping)
		startTime = time.clock()
		pingresult = iq.send()
		endTime = time.clock()
		if pingresult == False:
			return False
		return endTime - startTime
