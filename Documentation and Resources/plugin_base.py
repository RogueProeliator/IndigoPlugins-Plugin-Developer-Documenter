#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2013, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomo.com

import errno
import os
import select
import sys
import time
import traceback
import xml.dom.minidom
import re
import string
import threading

import serial  # TODO: serial library not a base install library.
import indigo

# Class PluginBase, defined below, will be automatically inserted into the
# "indigo" namespace by the host process. Any classes, functions, variables,
# etc., defined outside the PluginBase class scope will NOT be inserted.
#
# Additionally, the variable activePlugin is installed into the indigo global
# namespace. It always points to the active plugin instance (subclass of
# indigo.PluginBase, defined by plugin.py).

################################################################################
validDeviceTypes = ["dimmer", "relay", "sensor", "speedcontrol", "thermostat", "sprinkler", "custom"]

fieldTypeTemplates = {
	# Key is node <Field> type attribute, value is template file name.
	u"serialport": u"_configUiField_serialPort.xml"
}

################################################################################
################################################################################
class PluginBase(object):
	""" Base Indigo Plugin class that provides some default behaviors and utility functions. """
	############################################################################
	class StopThread(Exception):
		def __init__(self, value=None):
			self.value = value	# unicode string

	############################################################################
	menuItemsList = indigo.List()
	menuItemsDict = indigo.Dict()
	devicesTypeDict = indigo.Dict()
	eventsTypeDict = indigo.Dict()
	actionsTypeDict = indigo.Dict()

	########################################
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		# pluginPrefs is an Indigo dictionary object of all preferences which
		# are automatically loaded before we are initialized, and automatically
		# saved after shutdown().
		self.pluginId = pluginId
		self.pluginDisplayName = pluginDisplayName
		self.pluginVersion = pluginVersion
		self.pluginPrefs = pluginPrefs

		self.deviceFactoryXml = None

		# Parse the XML files and store the pieces we or other clients will need later.
		self._parseMenuItemsXML('MenuItems.xml')
		self._parseDevicesXML('Devices.xml')
		self._parseEventsXML('Events.xml')
		self._parseActionsXML('Actions.xml')

		# Create a pipe for efficient sleeping via select().
		self.stopThread = False
		self._stopThreadPipeIn, self._stopThreadPipeOut = os.pipe()

		# These member vars are used by convenience methods (not as critical as above).
		self.debug = False
		pass

	def __del__(self):
		pass

	########################################
	@staticmethod
	def versStrToTuple(versStr):
		cleaned = versStr
		if cleaned.find("alpha") >= 0:
			cleaned = cleaned[:cleaned.find("alpha")]
		elif cleaned.find("beta") >= 0:
			cleaned = cleaned[:cleaned.find("beta")]
		elif cleaned.find("a") >= 0:
			cleaned = cleaned[:cleaned.find("a")]
		elif cleaned.find("b") >= 0:
			cleaned = cleaned[:cleaned.find("b")]
		cleaned = cleaned.strip()
		verslist = cleaned.split(".")
		while len(verslist) < 4:
			verslist.append(u'0')
		return tuple(map(int, verslist))

	@staticmethod
	def versGreaterThanOrEq(cmpVersStr, baseVersStr):
		return PluginBase.versStrToTuple(cmpVersStr) >= PluginBase.versStrToTuple(baseVersStr)

	@staticmethod
	def serverVersCompatWith(versStr):
		return PluginBase.versGreaterThanOrEq(indigo.server.version, versStr)

	########################################
	def debugLog(self, msg):
		if self.debug:
			indigo.server.log(type=self.pluginDisplayName + u" Debug", message=msg)

	def errorLog(self, msg):
		indigo.server.log(message=msg, isError=True)

	def exceptionLog(self):
		try:
			self.errorLog(u"Error in plugin execution:\n\n" + traceback.format_exc(30))
		except:
			pass	# shouldn't ever throw, but don't raise if it does

	########################################
#	def startup(self):
#		self.debugLog(u"startup called")

	def _postStartup(self):
		self._deviceEnumAndStartComm()
		self._triggerEnumAndStartProcessing()

	########################################
#	def shutdown(self):
#		self.debugLog(u"shutdown called")

	def _preShutdown(self):
		self.stopConcurrentThread()
		self._triggerEnumAndStopProcessing()
		self._deviceEnumAndStopComm()

	########################################
	def prepareToSleep(self):
		self._triggerEnumAndStopProcessing()
		self._deviceEnumAndStopComm()

	########################################
	def wakeUp(self):
		self._deviceEnumAndStartComm()
		self._triggerEnumAndStartProcessing()

	########################################
#	def runConcurrentThread(self):
#		try:
#			while True:
#				self.debugLog(u"processing something...")
#				# Do your stuff here
#				self.Sleep(8)
#		except self.StopThread:
#			pass	# optionally catch the StopThread and do any needed cleanup

	########################################
	def stopConcurrentThread(self):
		self.stopThread = True
		os.write(self._stopThreadPipeOut, "*")

	########################################
	def stopPlugin(self, message="", isError=True):
		indigo.server.stopPlugin(message=message, isError=isError)

	########################################
	def sleep(self, seconds):
		if self.stopThread:
			raise self.StopThread
		if seconds <= 0.0:
			return

		curTime = time.time()
		stopTime = curTime + seconds
		while curTime < stopTime:
			try:
				select.select([self._stopThreadPipeIn], [], [], stopTime - curTime)
			except select.error, doh:
				# Select will throw "interrupted system call" EINTR if the process
				# receives a signal (IndigoServer can send them during kill requests).
				# Just ignore them (self.stopThread will be set on kill request) but
				# do raise up any other exceptions select() might throw.
				if doh[0] != errno.EINTR:
					raise
			if self.stopThread:
				raise self.StopThread
			curTime = time.time()

	########################################
	###################
	@staticmethod
	def _getChildElementsByTagName(elem, tagName):
		childList = []
		for child in elem.childNodes:
			if child.nodeType == child.ELEMENT_NODE and (tagName == u"*" or child.tagName == tagName):
				childList.append(child)
		return childList

	@staticmethod
	def _getXmlFromFile(filename):
		if not os.path.isfile(filename):
			return u""
		xml_file = file(filename, 'r')
		xml_data = xml_file.read()
		xml_file.close()
		return xml_data

	@staticmethod
	def _getXmlFromTemplate(templateName):
		filename = indigo.host.resourcesFolderPath + '/templates/' + templateName
		return PluginBase._getXmlFromFile(filename)

	@staticmethod
	def _getElementAttribute(elem, attrName, required=True, default=None, errorIfNotAscii=True):
		attrStr = elem.getAttribute(attrName)
		if attrStr is None or len(attrStr) == 0:
			if required:
				raise ValueError(u"required XML attribute '%s' is missing or empty" % (attrName,))
			return default
		elif errorIfNotAscii and attrStr[0] not in string.ascii_letters:
			raise ValueError(u"XML attribute '%s' has a value that starts with invalid characters: '%s' (should begin with A-Z or a-z):\n%s" % (attrName, attrStr, elem.toprettyxml()))
		return attrStr

	@staticmethod
	def _getElementValueByTagName(elem, tagName, required=True, default=None):
		valueElemList = PluginBase._getChildElementsByTagName(elem, tagName)
		if len(valueElemList) == 0:
			if required:
				raise ValueError(u"required XML element <%s> is missing" % (tagName,))
			return default
		elif len(valueElemList) > 1:
			raise ValueError(u"found more than one XML element <%s> (should only be one)" % (tagName,))

		valueStr = valueElemList[0].firstChild.data
		if valueStr is None or len(valueStr) == 0:
			if required:
				raise ValueError(u"required XML element <%s> is empty" % (tagName,))
			return default
		return valueStr

	###################
	def _parseMenuItemsXML(self, filename):
		if not os.path.isfile(filename):
			return
		try:
			dom = xml.dom.minidom.parseString(self._getXmlFromFile(filename))
		except:
			raise LookupError(filename + u" is malformed")
		menuItemsElem = self._getChildElementsByTagName(dom, u"MenuItems")
		if len(menuItemsElem) != 1:
			raise LookupError(u"Incorrect number of <MenuItems> elements found")

		menuItems = self._getChildElementsByTagName(menuItemsElem[0], u"MenuItem")
		for menu in menuItems:
			serverVers = self._getElementAttribute(menu, u"_minServerVers", required=False, errorIfNotAscii=False)
			if serverVers is not None and not PluginBase.serverVersCompatWith(serverVers):
				continue	# This version of Indigo Server isn't compatible with this object (skip it)

			menuDict = indigo.Dict()
			menuId = self._getElementAttribute(menu, u"id")
			if menuId in self.menuItemsDict:
				raise LookupError(u"Duplicate menu id found: " + menuId)

			menuDict[u"Id"] = menuId
			menuDict[u"Name"] = self._getElementValueByTagName(menu, u"Name", False)

			if "Name" in menuDict:
				menuDict[u"ButtonTitle"] = self._getElementValueByTagName(menu, u"ButtonTitle", False)

				# Plugin should specify at least a CallbackMethod or ConfigUIRawXml (possibly both)
				menuDict[u"CallbackMethod"] = self._getElementValueByTagName(menu, u"CallbackMethod", False)
				configUIList = self._getChildElementsByTagName(menu, u"ConfigUI")
				if len(configUIList) > 0:
					menuDict[u"ConfigUIRawXml"] = self._parseConfigUINode(dom, configUIList[0]).toxml()
				else:
					if not "CallbackMethod" in menuDict:
						raise ValueError(u"<MenuItem> elements must contain either a <CallbackMethod> and/or a <ConfigUI> element.")

			self.menuItemsList.append(menuDict)
			self.menuItemsDict[menuId] = menuDict

	###################
	def _swapTemplatedField(self, mainDom, configUI, refnode, templateFilename, fileInPluginSpace):
		if fileInPluginSpace:
			templateRaw = self._getXmlFromFile(templateFilename)
		else:
			templateRaw = self._getXmlFromTemplate(templateFilename)

		refId = self._getElementAttribute(refnode, u"id", False)
		if refId:
			templateRaw = templateRaw.replace("_FIELDID", refId)

		templateDom = xml.dom.minidom.parseString(templateRaw)
		templateNodes = self._getChildElementsByTagName(templateDom, u"Template")
		if len(templateNodes) != 1:
			raise LookupError(u"XML template file %s must have one root level <Template> node" % (templateFilename,))

		importFieldList = self._getChildElementsByTagName(templateNodes[0], u"Field")
		for importField in importFieldList:
			importField = mainDom.importNode(importField, True)
			configUI.insertBefore(importField, refnode)

		configUI.removeChild(refnode)
		return configUI

	def _parseConfigUINode(self, mainDom, configUI):
		# Parse all of the config Field nodes looking for any template
		# substitution that needs to occur. For example, <Field> nodes of
		# type="serialport" are substituted with the XML from file
		# _configUiField_serialPort.xml to provide a more complete multi-
		# field control that allows local serial ports and IP based
		# serial connections.
		fieldList = self._getChildElementsByTagName(configUI, u"Field")
		for refnode in fieldList:
			typeVal = self._getElementAttribute(refnode, u"type").lower()
			if typeVal in fieldTypeTemplates:
				self._swapTemplatedField(mainDom, configUI, refnode, fieldTypeTemplates[typeVal], False)

		fieldList = self._getChildElementsByTagName(configUI, u"Template")
		for refnode in fieldList:
			filename = self._getElementAttribute(refnode, u"file")
			if filename:
				self._swapTemplatedField(mainDom, configUI, refnode, filename, True)

		# self.debugLog(u"configUI:\n" + configUI.toxml() + "\n")
		return configUI

	###################
	# TODO: @staticMethod?
	def _getDeviceStateDictForType(self, type, stateId, triggerLabel, controlPageLabel, disabled=False):
		stateDict = indigo.Dict()
		stateDict[u"Type"] = int(type)
		stateDict[u"Key"] = stateId
		stateDict[u"Disabled"] = disabled
		stateDict[u"TriggerLabel"] = triggerLabel
		stateDict[u"StateLabel"] = controlPageLabel
		return stateDict

	def getDeviceStateDictForSeparator(self, stateId):
		return self._getDeviceStateDictForType(indigo.kTriggerKeyType.Label, stateId, u"_Separator", u"_Separator", True)
	def getDeviceStateDictForSeperator(self, stateId):
		return self.getDeviceStateDictForSeparator(stateId)

	def getDeviceStateDictForNumberType(self, stateId, triggerLabel, controlPageLabel, disabled=False):
		return self._getDeviceStateDictForType(indigo.kTriggerKeyType.Number, stateId, triggerLabel, controlPageLabel, disabled)

	def getDeviceStateDictForStringType(self, stateId, triggerLabel, controlPageLabel, disabled=False):
		return self._getDeviceStateDictForType(indigo.kTriggerKeyType.String, stateId, triggerLabel, controlPageLabel, disabled)

	def getDeviceStateDictForEnumType(self, stateId, triggerLabel, controlPageLabel, disabled=False):
		return self._getDeviceStateDictForType(indigo.kTriggerKeyType.Enumeration, stateId, triggerLabel, controlPageLabel, disabled)

	def getDeviceStateDictForBoolOnOffType(self, stateId, triggerLabel, controlPageLabel, disabled=False):
		stateDict = self._getDeviceStateDictForType(indigo.kTriggerKeyType.BoolOnOff, stateId, triggerLabel, controlPageLabel, disabled)
		stateDict[u"StateLabel"] = stateDict[u"StateLabel"] + u" (on or off)"
		return stateDict

	def getDeviceStateDictForBoolYesNoType(self, stateId, triggerLabel, controlPageLabel, disabled=False):
		stateDict = self._getDeviceStateDictForType(indigo.kTriggerKeyType.BoolYesNo, stateId, triggerLabel, controlPageLabel, disabled)
		stateDict[u"StateLabel"] = stateDict[u"StateLabel"] + u" (yes or no)"
		return stateDict

	def getDeviceStateDictForBoolOneZeroType(self, stateId, triggerLabel, controlPageLabel, disabled=False):
		stateDict = self._getDeviceStateDictForType(indigo.kTriggerKeyType.BoolOneZero, stateId, triggerLabel, controlPageLabel, disabled)
		stateDict[u"StateLabel"] = stateDict[u"StateLabel"] + u" (1 or 0)"
		return stateDict

	def getDeviceStateDictForBoolTrueFalseType(self, stateId, triggerLabel, controlPageLabel, disabled=False):
		stateDict = self._getDeviceStateDictForType(indigo.kTriggerKeyType.BoolTrueFalse, stateId, triggerLabel, controlPageLabel, disabled)
		stateDict[u"StateLabel"] = stateDict[u"StateLabel"] + u" (true or false)"
		return stateDict

	def _parseDevicesXML(self, filename):
		if not os.path.isfile(filename):
			return
		try:
			dom = xml.dom.minidom.parseString(self._getXmlFromFile(filename))
		except Exception, e:
			self.errorLog(filename + u" has an error: %s" % str(e))
			raise LookupError(filename + u" is malformed")

		# Now get all devices from the <Devices> element
		devicesElement = self._getChildElementsByTagName(dom, u"Devices")
		if len(devicesElement) != 1:
			raise LookupError(u"Incorrect number of <Devices> elements found")

		# Look for a DeviceFactory element - that will be used to create devices
		# rather than creating them directly using the <Device> XML. This allows
		# a plugin to discover device types rather than forcing the user to select
		# the type up-front (like how INSTEON devices are added).
		deviceFactoryElements = self._getChildElementsByTagName(devicesElement[0], u"DeviceFactory")
		if len(deviceFactoryElements) > 1:
			raise LookupError(u"Incorrect number of <DeviceFactory> elements found")
		elif len(deviceFactoryElements) == 1:
			deviceFactory = deviceFactoryElements[0]
			elems = self._getChildElementsByTagName(deviceFactory, u"Name")
			if len(elems) != 1:
				raise LookupError(u"<DeviceFactory> element must contain exactly one <Name> element")
			elems = self._getChildElementsByTagName(deviceFactory, u"ButtonTitle")
			if len(elems) != 1:
				raise LookupError(u"<DeviceFactory> element must contain exactly one <ButtonTitle> element")
			elems = self._getChildElementsByTagName(deviceFactory, u"ConfigUI")
			if len(elems) != 1:
				raise LookupError(u"<DeviceFactory> element must contain exactly one <ConfigUI> element")
			self.deviceFactoryXml = deviceFactory.toxml()
		else:
			self.deviceFactoryXml = None

		sortIndex = 0
		deviceElemList = self._getChildElementsByTagName(devicesElement[0], u"Device")
		for device in deviceElemList:
			serverVers = self._getElementAttribute(device, u"_minServerVers", required=False, errorIfNotAscii=False)
			if serverVers is not None and not PluginBase.serverVersCompatWith(serverVers):
				continue	# This version of Indigo Server isn't compatible with this object (skip it)

			deviceDict = indigo.Dict()
			deviceTypeId = self._getElementAttribute(device, u"id")
			if deviceTypeId in self.devicesTypeDict:
				raise LookupError(u"Duplicate device type id found: " + deviceTypeId)
			deviceDict[u"Type"] = self._getElementAttribute(device, u"type")
			if deviceDict[u"Type"] not in validDeviceTypes:
				raise LookupError(u"Unknown device type in Devices.xml")
			deviceDict[u"Name"] = self._getElementValueByTagName(device, u"Name")
			deviceDict[u"DisplayStateId"] = self._getElementValueByTagName(device, u"UiDisplayStateId", required=False, default=u"")
			deviceDict[u"SortOrder"] = sortIndex
			sortIndex += 1

			configUIList = self._getChildElementsByTagName(device, u"ConfigUI")
			if len(configUIList) > 0:
				deviceDict[u"ConfigUIRawXml"] = self._parseConfigUINode(dom, configUIList[0]).toxml()

			deviceStatesElementList = self._getChildElementsByTagName(device, u"States")
			statesList = indigo.List()
			if len(deviceStatesElementList) > 1:
				raise LookupError(u"Incorrect number of <States> elements found")
			elif len(deviceStatesElementList) == 1:
				deviceStateElements = self._getChildElementsByTagName(deviceStatesElementList[0], u"State")
				for state in deviceStateElements:
					stateId = self._getElementAttribute(state, u"id")
					triggerLabel = self._getElementValueByTagName(state, u"TriggerLabel", required=False, default=u"")
					controlPageLabel = self._getElementValueByTagName(state, u"ControlPageLabel", required=False, default=u"")

					disabled = False	# ToDo: need to read this?
					stateValueTypes = self._getChildElementsByTagName(state, u"ValueType")
					if len(stateValueTypes) != 1:
						raise LookupError(u"<State> elements must have exactly one <ValueType> element")

					valueListElements = self._getChildElementsByTagName(stateValueTypes[0], u"List")
					if len(valueListElements) > 1:
						raise LookupError(u"<ValueType> elements must have zero or one <List> element")
					elif len(valueListElements) == 1:
						# It must have a TriggerLabel and a ControlPageLabel
						if (triggerLabel == "") or (controlPageLabel == ""):
							raise LookupError(u"State elements must have both a TriggerLabel and a ControlPageLabel")
						# It's an enumeration -- add an enum type for triggering off of any changes
						# to this enumeration type:
						stateDict = self.getDeviceStateDictForEnumType(stateId, triggerLabel, controlPageLabel, disabled)
						statesList.append(stateDict)

						# And add individual true/false types for triggering off every enumeration
						# value possibility (as specified by the Option list):
						triggerLabelPrefix = self._getElementValueByTagName(state, u"TriggerLabelPrefix", required=False, default=u"")
						controlPageLabelPrefix = self._getElementValueByTagName(state, u"ControlPageLabelPrefix", required=False, default=u"")

						valueOptions = self._getChildElementsByTagName(valueListElements[0], u"Option")
						if len(valueOptions) < 1:
							raise LookupError(u"<List> elements must have at least one <Option> element")
						for option in valueOptions:
							subStateId = stateId + u"." + self._getElementAttribute(option, u"value")

							if len(triggerLabelPrefix) > 0:
								subTriggerLabel = triggerLabelPrefix + u" " + option.firstChild.data
							else:
								subTriggerLabel = option.firstChild.data

							if len(controlPageLabelPrefix) > 0:
								subControlPageLabel = controlPageLabelPrefix + u" " + option.firstChild.data
							else:
								subControlPageLabel = option.firstChild.data

							subDisabled = False	# ToDo: need to read this?

							subStateDict = self.getDeviceStateDictForBoolTrueFalseType(subStateId, subTriggerLabel, subControlPageLabel, subDisabled)
							statesList.append(subStateDict)
					else:
						# It's not an enumeration
						stateDict = None
						valueType = stateValueTypes[0].firstChild.data.lower()
						# It must have a TriggerLabel and a ControlPageLabel if it's not a separator
						if (valueType != u"separator"):
							if (triggerLabel == "") or (controlPageLabel == ""):
								raise LookupError(u"State elements must have both a TriggerLabel and a ControlPageLabel")
						if valueType == u"boolean":
							boolType = stateValueTypes[0].getAttribute(u"boolType").lower()
							if boolType == u"onoff":
								stateDict = self.getDeviceStateDictForBoolOnOffType(stateId, triggerLabel, controlPageLabel, disabled)
							elif boolType == u"yesno":
								stateDict = self.getDeviceStateDictForBoolYesNoType(stateId, triggerLabel, controlPageLabel, disabled)
							elif boolType == u"onezero":
								stateDict = self.getDeviceStateDictForBoolOneZeroType(stateId, triggerLabel, controlPageLabel, disabled)
							else:
								stateDict = self.getDeviceStateDictForBoolTrueFalseType(stateId, triggerLabel, controlPageLabel, disabled)
						elif valueType == u"number" or valueType == u"float" or valueType == u"integer":
							stateDict = self.getDeviceStateDictForNumberType(stateId, triggerLabel, controlPageLabel, disabled)
						elif valueType == u"string":
							stateDict = self.getDeviceStateDictForStringType(stateId, triggerLabel, controlPageLabel, disabled)
						elif valueType == u"separator":
							stateDict = self.getDeviceStateDictForSeparator(stateId)

						if stateDict:
							statesList.append(stateDict)
			deviceDict[u"States"] = statesList

			self.devicesTypeDict[deviceTypeId] = deviceDict

	###################
	def _parseEventsXML(self, filename):
		if not os.path.isfile(filename):
			return
		try:
			dom = xml.dom.minidom.parseString(self._getXmlFromFile(filename))
		except:
			raise LookupError(filename + u" is malformed")
		eventsElement = self._getChildElementsByTagName(dom, u"Events")
		if len(eventsElement) != 1:
			raise LookupError(u"Incorrect number of <Events> elements found")

		sortIndex = 0
		eventElemList = self._getChildElementsByTagName(eventsElement[0], u"Event")
		for event in eventElemList:
			serverVers = self._getElementAttribute(event, u"_minServerVers", required=False, errorIfNotAscii=False)
			if serverVers is not None and not PluginBase.serverVersCompatWith(serverVers):
				continue	# This version of Indigo Server isn't compatible with this object (skip it)

			eventDict = indigo.Dict()
			eventTypeId = self._getElementAttribute(event, u"id")
			if eventTypeId in self.eventsTypeDict:
				raise LookupError(u"Duplicate event type id found: " + eventTypeId)
			try:
				eventDict[u"Name"] = self._getElementValueByTagName(event, u"Name")
			except ValueError:
				# It's missing <Name> so treat it as a separator
				eventDict[u"Name"] = u" - "
			eventDict[u"SortOrder"] = sortIndex
			sortIndex += 1

			configUIList = self._getChildElementsByTagName(event, u"ConfigUI")
			if len(configUIList) > 0:
				eventDict[u"ConfigUIRawXml"] = self._parseConfigUINode(dom, configUIList[0]).toxml()

			self.eventsTypeDict[eventTypeId] = eventDict

	###################
	def _parseActionsXML(self, filename):
		if not os.path.isfile(filename):
			return
		try:
			dom = xml.dom.minidom.parseString(self._getXmlFromFile(filename))
		except:
			raise LookupError(filename + u" is malformed")
		actionsElement = self._getChildElementsByTagName(dom, u"Actions")
		if len(actionsElement) != 1:
			raise LookupError(u"Incorrect number of <Actions> elements found")

		sortIndex = 0
		actionElemList = self._getChildElementsByTagName(actionsElement[0], u"Action")
		for action in actionElemList:
			serverVers = self._getElementAttribute(action, u"_minServerVers", required=False, errorIfNotAscii=False)
			if serverVers is not None and not PluginBase.serverVersCompatWith(serverVers):
				continue	# This version of Indigo Server isn't compatible with this object (skip it)

			actionDict = indigo.Dict()
			actionTypeId = self._getElementAttribute(action, u"id")
			if actionTypeId in self.actionsTypeDict:
				raise LookupError(u"Duplicate action type id found: " + actionTypeId)
			try:
				actionDict[u"Name"] = self._getElementValueByTagName(action, u"Name")
				actionDict[u"CallbackMethod"] = self._getElementValueByTagName(action, u"CallbackMethod")
				actionDict[u"DeviceFilter"] = self._getElementAttribute(action, u"deviceFilter", False, u"")
			except ValueError:
				# It's missing <Name> or <CallbackMethod> so treat it as a separator
				actionDict[u"Name"] = u" - "
				actionDict[u"CallbackMethod"] = u""
				actionDict[u"DeviceFilter"] = u""
			actionDict[u"UiPath"] = self._getElementAttribute(action, u"uiPath", required=False)
			actionDict[u"PrivateUiPath"] = self._getElementAttribute(action, u"privateUiPath", required=False)
			actionDict[u"SortOrder"] = sortIndex
			sortIndex += 1

			configUIList = self._getChildElementsByTagName(action, u"ConfigUI")
			if len(configUIList) > 0:
				actionDict[u"ConfigUIRawXml"] = self._parseConfigUINode(dom, configUIList[0]).toxml()

			self.actionsTypeDict[actionTypeId] = actionDict

	################################################################################
	########################################
	# TODO: @staticMethod?
	def doesPrefsConfigUiExist(self):
		return os.path.isfile('PluginConfig.xml')

	def getPrefsConfigUiXml(self):
		dom = xml.dom.minidom.parseString(self._getXmlFromFile('PluginConfig.xml'))
		configUIList = self._getChildElementsByTagName(dom, u"PluginConfig")
		if len(configUIList) != 1:
			raise LookupError(u"PluginConfig.xml file must have one root level <PluginConfig> node")
		return self._parseConfigUINode(dom, configUIList[0]).toxml()

	def getPrefsConfigUiValues(self):
		valuesDict = self.pluginPrefs
		errorMsgDict = indigo.Dict()
		return (valuesDict, errorMsgDict)

	def validatePrefsConfigUi(self, valuesDict):
		return (True, valuesDict)
		#	Or if UI is not valid use:
		# errorMsgDict = indigo.Dict()
		# errorMsgDict[u"someUiFieldId"] = u"sorry but you MUST check this checkbox!"
		# return (False, valuesDict, errorMsgDict)

	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		return

	########################################
	def getMenuItemsList(self):
		return self.menuItemsList

	def getMenuActionConfigUiXml(self, menuId):
		if menuId in self.menuItemsDict:
			rawXML = self.menuItemsDict[menuId][u"ConfigUIRawXml"]
			return rawXML
		return None

	def getMenuActionConfigUiValues(self, menuId):
		valuesDict = indigo.Dict()
		errorMsgDict = indigo.Dict()
		return (valuesDict, errorMsgDict)

# Currently, menu actions never validate UI on closure. If this changes at some
# point then we'll need these:
#
#	def validateMenuActionConfigUi(self, valuesDict, menuId):
#		return (True, valuesDict)
#
#	def closedMenuActionConfigUi(self, valuesDict, userCancelled, menuId):
#		return

	########################################
	def getDevicesDict(self):
		return self.devicesTypeDict

	def getDeviceStateList(self, dev):
		if dev.deviceTypeId in self.devicesTypeDict:
			return self.devicesTypeDict[dev.deviceTypeId][u"States"]
		return None

	def getDeviceDisplayStateId(self, dev):
		if dev.deviceTypeId in self.devicesTypeDict:
			return self.devicesTypeDict[dev.deviceTypeId][u"DisplayStateId"]
		return None

	def getDeviceTypeClassName(self, typeId):
		if typeId in self.devicesTypeDict:
			return self.devicesTypeDict[typeId][u"Type"]
		return None

	###################
	def getDeviceConfigUiXml(self, typeId, devId):
		if typeId in self.devicesTypeDict:
			return self.devicesTypeDict[typeId][u"ConfigUIRawXml"]
		return None

	def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
		valuesDict = pluginProps
		errorMsgDict = indigo.Dict()
		return (valuesDict, errorMsgDict)

	def validateDeviceConfigUi(self, valuesDict, typeId, devId):
		return (True, valuesDict)
		#	Or if UI is not valid use:
		# errorMsgDict = indigo.Dict()
		# errorMsgDict[u"someUiFieldId"] = u"sorry but you MUST check this checkbox!"
		# return (False, valuesDict, errorMsgDict)

	def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
		return

	###################
	def doesDeviceFactoryExist(self):
		return self.deviceFactoryXml is not None

	def getDeviceFactoryUiXml(self):
		return self.deviceFactoryXml

	def getDeviceFactoryUiValues(self, devIdList):
		valuesDict = indigo.Dict()
		errorMsgDict = indigo.Dict()
		return (valuesDict, errorMsgDict)

	def validateDeviceFactoryUi(self, valuesDict, devIdList):
		return (True, valuesDict)
		#	Or if UI is not valid use:
		# errorMsgDict = indigo.Dict()
		# errorMsgDict[u"someUiFieldId"] = u"sorry but you MUST check this checkbox!"
		# return (False, valuesDict, errorMsgDict)

	def closedDeviceFactoryUi(self, valuesDict, userCancelled, devIdList):
		return

	########################################
	def getEventsDict(self):
		return self.eventsTypeDict

	def getEventConfigUiXml(self, typeId, eventId):
		if typeId in self.eventsTypeDict:
			return self.eventsTypeDict[typeId][u"ConfigUIRawXml"]
		return None

	def getEventConfigUiValues(self, pluginProps, typeId, eventId):
		valuesDict = pluginProps
		errorMsgDict = indigo.Dict()
		return (valuesDict, errorMsgDict)

	def validateEventConfigUi(self, valuesDict, typeId, eventId):
		return (True, valuesDict)
		#	Or if UI is not valid use:
		# errorMsgDict = indigo.Dict()
		# errorMsgDict[u"someUiFieldId"] = u"sorry but you MUST check this checkbox!"
		# return (False, valuesDict, errorMsgDict)

	def closedEventConfigUi(self, valuesDict, userCancelled, typeId, eventId):
		return

	########################################
	def getActionsDict(self):
		return self.actionsTypeDict

	def getActionCallbackMethod(self, typeId):
		if typeId in self.actionsTypeDict:
			return self.actionsTypeDict[typeId][u"CallbackMethod"]
		return None

	def getActionConfigUiXml(self, typeId, devId):
		if typeId in self.actionsTypeDict:
			return self.actionsTypeDict[typeId][u"ConfigUIRawXml"]
		return None

	def getActionConfigUiValues(self, pluginProps, typeId, devId):
		valuesDict = pluginProps
		errorMsgDict = indigo.Dict()
		return (valuesDict, errorMsgDict)

	def validateActionConfigUi(self, valuesDict, typeId, devId):
		return (True, valuesDict)
		#	Or if UI is not valid use:
		# errorMsgDict = indigo.Dict()
		# errorMsgDict[u"someUiFieldId"] = u"sorry but you MUST check this checkbox!"
		# return (False, valuesDict, errorMsgDict)

	def closedActionConfigUi(self, valuesDict, userCancelled, typeId, devId):
		return

	################################################################################
	########################################
	def _deviceEnumAndStartComm(self):
		for elem in indigo.devices.iter(self.pluginId):
			if elem.configured and elem.enabled:
				try:
					self.deviceStartComm(elem)
				except Exception, e:
					self.errorLog(u"exception in deviceStartComm(%s): %s" % (elem.name, str(e)))
				except:
					self.errorLog(u"exception in deviceStartComm(%s)" % (elem.name,))

	def _deviceEnumAndStopComm(self):
		for elem in indigo.devices.iter(self.pluginId):
			if elem.configured and elem.enabled:
				try:
					self.deviceStopComm(elem)
				except Exception, e:
					self.errorLog(u"exception in deviceStopComm(%s): %s" % (elem.name, str(e)))
				except:
					self.errorLog(u"exception in deviceStopComm(%s)" % (elem.name,))

	def didDeviceCommPropertyChange(self, origDev, newDev):
		# Return True if a plugin related property changed from
		# origDev to newDev. Examples would be serial port,
		# IP address, etc. By default we assume all properties
		# are comm related, but plugin can subclass to provide
		# more specific/optimized testing. The return val of
		# this method will effect when deviceStartComm() and
		# deviceStopComm() are called.
		if origDev.pluginProps != newDev.pluginProps:
			return True
		return False

	def deviceStartComm(self, dev):
		# self.debugLog(u"deviceStartComm: " + dev.name)
		pass

	def deviceStopComm(self, dev):
		# self.debugLog(u"deviceStopComm: " + dev.name)
		pass

	def deviceCreated(self, dev):
		# self.debugLog(u"deviceCreated: \n" + str(dev))
		if dev.pluginId != self.pluginId:
			return		# device is not plugin based -- bail out

		if dev.configured and dev.enabled:
			self.deviceStartComm(dev)

	def deviceDeleted(self, dev):
		# self.debugLog(u"deviceDeleted: \n" + str(dev))
		if dev.pluginId != self.pluginId:
			return		# device is not plugin based -- bail out

		if dev.configured and dev.enabled:
			self.deviceStopComm(dev)

	def deviceUpdated(self, origDev, newDev):
		# self.debugLog(u"deviceUpdated orig: \n" + str(origDev))
		# self.debugLog(u"deviceUpdated new: \n" + str(newDev))
		origDevPluginId = origDev.pluginId
		newDevPluginId = newDev.pluginId
		if origDevPluginId != self.pluginId and newDevPluginId != self.pluginId:
			return		# neither is a plugin based device -- bail out

		origDevTypeId = origDev.deviceTypeId
		newDevTypeId = newDev.deviceTypeId

		commPropChanged = False
		if origDevPluginId != newDevPluginId:
			commPropChanged = True
		elif origDevTypeId != newDevTypeId:
			commPropChanged = True
		elif (origDev.configured and origDev.enabled) != (newDev.configured and newDev.enabled):
			commPropChanged = True
		elif newDev.configured:
			commPropChanged = self.didDeviceCommPropertyChange(origDev, newDev)

		if not commPropChanged:
			return		# no comm related properties changed -- bail out

		# If we get this far then there was a significant enough
		# change (property, pluginId, enable state) to warrant
		# a call to stop the previous device comm and restart
		# the new device comm.
		if origDevPluginId == self.pluginId:
			if origDev.configured and origDev.enabled:
				self.deviceStopComm(origDev)
		if newDevPluginId == self.pluginId:
			if newDev.configured and newDev.enabled:
				self.deviceStartComm(newDev)

	########################################
	def _triggerGetPluginId(self, trigger):
		if not isinstance(trigger, indigo.PluginEventTrigger):
			return None
		return trigger.pluginId

	def _triggerGetPluginTypeId(self, trigger):
		if not isinstance(trigger, indigo.PluginEventTrigger):
			return None
		return trigger.pluginTypeId

	def _triggerEnumAndStartProcessing(self):
		for elem in indigo.triggers.iter(self.pluginId):
			if elem.configured and elem.enabled:
				try:
					self.triggerStartProcessing(elem)
				except Exception, e:
					self.errorLog(u"exception in triggerStartProcessing(%s): %s" % (elem.name, str(e)))
				except:
					self.errorLog(u"exception in triggerStartProcessing(%s)" % (elem.name,))

	def _triggerEnumAndStopProcessing(self):
		for elem in indigo.triggers.iter(self.pluginId):
			if elem.configured and elem.enabled:
				try:
					self.triggerStopProcessing(elem)
				except Exception, e:
					self.errorLog(u"exception in triggerStopProcessing(%s): %s" % (elem.name, str(e)))
				except:
					self.errorLog(u"exception in triggerStopProcessing(%s)" % (elem.name,))

	def didTriggerProcessingPropertyChange(self, origTrigger, newTrigger):
		# Return True if a plugin related property changed from
		# origTrigger to newTrigger. Examples would be serial port,
		# IP address, etc. By default we assume all properties
		# are comm related, but plugin can subclass to provide
		# more specific/optimized testing. The return val of
		# this method will effect when triggerStartProcessing() and
		# triggerStopProcessing() are called.
		if origTrigger.pluginProps != newTrigger.pluginProps:
			return True
		return False

	def triggerStartProcessing(self, trigger):
		# self.debugLog(u"triggerStartProcessing: " + trigger.name)
		pass

	def triggerStopProcessing(self, trigger):
		# self.debugLog(u"triggerStopProcessing: " + trigger.name)
		pass

	def triggerCreated(self, trigger):
		# self.debugLog(u"triggerCreated: \n" + str(trigger))
		if self._triggerGetPluginId(trigger) != self.pluginId:
			return		# trigger is not plugin based -- bail out

		if trigger.configured and trigger.enabled:
			self.triggerStartProcessing(trigger)

	def triggerDeleted(self, trigger):
		# self.debugLog(u"triggerDeleted: \n" + str(trigger))
		if self._triggerGetPluginId(trigger) != self.pluginId:
			return		# trigger is not plugin based -- bail out

		if trigger.configured and trigger.enabled:
			self.triggerStopProcessing(trigger)

	def triggerUpdated(self, origTrigger, newTrigger):
		# self.debugLog(u"triggerUpdated orig: \n" + str(origTrigger))
		# self.debugLog(u"triggerUpdated new: \n" + str(newTrigger))
		origTriggerPluginId = self._triggerGetPluginId(origTrigger)
		newTriggerPluginId = self._triggerGetPluginId(newTrigger)
		if origTriggerPluginId != self.pluginId and newTriggerPluginId != self.pluginId:
			return		# neither is a plugin based trigger -- bail out

		origTriggerTypeId = self._triggerGetPluginTypeId(origTrigger)
		newTriggerTypeId = self._triggerGetPluginTypeId(newTrigger)

		processingPropChanged = False
		if origTriggerPluginId != newTriggerPluginId:
			processingPropChanged = True
		elif origTriggerTypeId != newTriggerTypeId:
			processingPropChanged = True
		elif (origTrigger.configured and origTrigger.enabled) != (newTrigger.configured and newTrigger.enabled):
			processingPropChanged = True
		elif newTrigger.configured:
			processingPropChanged = self.didTriggerProcessingPropertyChange(origTrigger, newTrigger)

		if not processingPropChanged:
			return		# no processing related properties changed -- bail out

		# If we get this far then there was a significant enough
		# change (property, pluginId, enable state) to warrant
		# a call to stop the previous trigger processing and restart
		# the new trigger processing.
		if origTriggerPluginId == self.pluginId:
			if origTrigger.configured and origTrigger.enabled:
				self.triggerStopProcessing(origTrigger)
		if newTriggerPluginId == self.pluginId:
			if newTrigger.configured and newTrigger.enabled:
				self.triggerStartProcessing(newTrigger)

	########################################
	def scheduleCreated(self, schedule):
		# self.debugLog(u"scheduleCreated: \n" + str(schedule))
		pass

	def scheduleDeleted(self, schedule):
		# self.debugLog(u"scheduleDeleted: \n" + str(schedule))
		pass

	def scheduleUpdated(self, origSchedule, newSchedule):
		# self.debugLog(u"scheduleUpdated orig: \n" + str(origSchedule))
		# self.debugLog(u"scheduleUpdated new: \n" + str(newSchedule))
		pass

	########################################
	def actionGroupCreated(self, group):
		# self.debugLog(u"actionGroupCreated: \n" + str(group))
		pass

	def actionGroupDeleted(self, group):
		# self.debugLog(u"actionGroupDeleted: \n" + str(group))
		pass

	def actionGroupUpdated(self, origGroup, newGroup):
		# self.debugLog(u"actionGroupUpdated orig: \n" + str(origGroup))
		# self.debugLog(u"actionGroupUpdated new: \n" + str(newGroup))
		pass

	########################################
	def controlPageCreated(self, page):
		# self.debugLog(u"controlPageCreated: \n" + str(page))
		pass

	def controlPageDeleted(self, page):
		# self.debugLog(u"controlPageDeleted: \n" + str(page))
		pass

	def controlPageUpdated(self, origPage, newPage):
		# self.debugLog(u"controlPageUpdated orig: \n" + str(origPage))
		# self.debugLog(u"controlPageUpdated new: \n" + str(newPage))
		pass

	########################################
	def variableCreated(self, var):
		# self.debugLog(u"variableCreated: \n" + str(var))
		pass

	def variableDeleted(self, var):
		# self.debugLog(u"variableDeleted: \n" + str(var))
		pass

	def variableUpdated(self, origVar, newVar):
		# self.debugLog(u"variableUpdated orig: \n" + str(origVar))
		# self.debugLog(u"variableUpdated new: \n" + str(newVar))
		pass

	################################################################################
	########################################
	def applicationWithBundleIdentifier(self, bundleID):
		from ScriptingBridge import SBApplication  # TODO: SBApplicatiion reference not found
		return SBApplication.applicationWithBundleIdentifier_(bundleID)

	########################################
	def browserOpen(self, url):
		# We originally tried using webbrowser.open_new(url) but it
		# seems quite buggy, so instead we'll let IPH handle it:
		indigo.host.browserOpen(url)

	########################################
	def _insertVariableValue(self, matchobj):
		try:
			theVarValue = indigo.variables[int(matchobj.group(1))].value
		except:
			theVarValue = ""
			self.errorLog(u"Variable id " + matchobj.group(1) + u" not found for substitution")
		return theVarValue

	###################
	def substituteVariable(self, inString, validateOnly=False):
		validated = True
		variableValue = None
		stringParts = inString.split("%%")
		for substr in stringParts:
			if substr[0:2] == "v:":
				varNameTuple = substr.split(":")
				varIdString = varNameTuple[1]
				if varIdString.find(" ") < 0:
					try:
						varId = int(varIdString)
						theVariable = indigo.variables.get(varId, None)
						if theVariable is None:
							validated = False
						else:
							variableValue = theVariable.value
					except:
						validated = False
				else:
					validated = False
		if validateOnly:
			if validated:
				return (validated,)
			else:
				return (validated, u"Either a variable ID doesn't exist or there's a substitution format error")
		else:
			p = re.compile("\%%v:([0-9]*)%%")
			newString = p.sub(self._insertVariableValue, inString)
			return newString
	
	########################################
	def _insertStateValue(self, matchobj):
		try:
			theStateValue = unicode(indigo.devices[int(matchobj.group(1))].states[matchobj.group(2)])
		except:
			theStateValue = ""
			self.errorLog(u"Device id " + matchobj.group(1) + u" or state id " + matchobj.group(2) + u" not found for substitution")
		return theStateValue

	###################
	def substituteDeviceState(self, inString, validateOnly=False):
		validated = True
		stateValue = None
		stringParts = inString.split("%%")
		for substr in stringParts:
			if substr[0:2] == "d:":
				devParts = substr.split(":")
				if (len(devParts) != 3):
					validated = False
				else:
					devIdString = devParts[1]
					devStateName = devParts[2]
					if devIdString.find(" ") < 0:
						try:
							devId = int(devIdString)
							theDevice = indigo.devices.get(devId, None)
							if theDevice is None:
								validated = False
							else:
								stateValue = theDevice.states[devStateName]  # TODO: Unless I'm mistaken, you can't get here.  Syntax checkng is calling this a new local variable.
						except:
							validated = False
					else:
						validated = False
		if validateOnly:
			if validated:
				return (validated,)
			else:
				return (validated, u"Either a device ID or state doesn't exist or there's a substitution format error")
		else:
			p = re.compile("\%%d:([0-9]*):([A-z0-9]*)%%")
			newString = p.sub(self._insertStateValue, inString)
			return newString

	########################################
	def substitute(self, inString, validateOnly=False):
		results = self.substituteVariable(inString, validateOnly)
		if isinstance(results, tuple):
			if results[0]:
				results = inString
			else:
				return results
		results = self.substituteDeviceState(results, validateOnly)
		return results

	########################################
	# Utility method to be called from plugin's validatePrefsConfigUi, validateDeviceConfigUi, etc.
	# methods. Used to make sure that a valid serial port is chosen. Caller should pass any non-None
	# tuple results up to the IPH caller (if None is returned then serial UI is valid and they
	# should continue with any other validation).
	def validateSerialPortUi(self, valuesDict, errorsDict, fieldId):
		connTypeKey = fieldId + u'_serialConnType'
		uiAddressKey = fieldId + u'_uiAddress'
		if valuesDict[connTypeKey] == u"local":
			localKey = fieldId + u'_serialPortLocal'
			valuesDict[uiAddressKey] = valuesDict[localKey]
			if len(valuesDict[localKey]) == 0:
				# User has not selected a valid serial port -- show an error.
				errorsDict[localKey] = u"Select a valid serial port. If none are listed, then make sure you have installed the FTDI VCP driver."
				return False
		elif valuesDict[connTypeKey] == u"netSocket":
			netSocketKey = fieldId + u'_serialPortNetSocket'
			netSocket = valuesDict.get(netSocketKey, u"")
			netSocket = netSocket.replace(u"socket://", u"")
			netSocket = netSocket.replace(u"rfc2217://", u"")
			valuesDict[netSocketKey] = u"socket://" + netSocket
			valuesDict[uiAddressKey] = netSocket
			try:
				if len(netSocket) == 0:
					raise ValueError("empty URL")
				stripped = netSocket
				if '/' in stripped:
					stripped, options = stripped.split('/', 1)
				host, port = stripped.split(':', 1)
				port = int(port)
				if not 0 <= port < 65536:
					raise ValueError("port not in range 0...65535")
			except ValueError:
				errorsDict[netSocketKey] = u"Enter a valid network IP address and port for the remote serial server (ex: socket://192.168.1.160:8123)."
				return False
		elif valuesDict[connTypeKey] == u"netRfc2217":
			netRfc2217Key = fieldId + u'_serialPortNetRfc2217'
			netRfc2217 = valuesDict.get(netRfc2217Key, u"")
			netRfc2217 = netRfc2217.replace(u"socket://", u"")
			netRfc2217 = netRfc2217.replace(u"rfc2217://", u"")
			valuesDict[netRfc2217Key] = u"rfc2217://" + netRfc2217
			valuesDict[uiAddressKey] = netRfc2217
			try:
				if len(netRfc2217) == 0:
					raise ValueError("empty URL")
				stripped = netRfc2217
				if '/' in stripped:
					stripped, options = stripped.split('/', 1)
				host, port = stripped.split(':', 1)
				port = int(port)
				if not 0 <= port < 65536:
					raise ValueError("port not in range 0...65535")
			except ValueError:
				errorsDict[netRfc2217Key] = u"Enter a valid network IP address and port for the remote serial server (ex: rfc2217://192.168.1.160:8123)."
				return False
		else:
			valuesDict[uiAddressKey] = u""
			errorsDict[connTypeKey] = u"Valid serial connection type not selected."
			return False
		return True

	def getSerialPortUrl(self, propsDict, fieldId):
		try:
			connTypeKey = fieldId + u'_serialConnType'
			if propsDict[connTypeKey] == u"local":
				localKey = fieldId + u'_serialPortLocal'
				return propsDict[localKey]
			elif propsDict[connTypeKey] == u"netSocket":
				netSocketKey = fieldId + u'_serialPortNetSocket'
				netSocket = propsDict.get(netSocketKey, u"")
				if not netSocket.lower().startswith("socket://"):
					netSocket = u"socket://" + netSocket
				return netSocket
			elif propsDict[connTypeKey] == u"netRfc2217":
				netRfc2217Key = fieldId + u'_serialPortNetRfc2217'
				netRfc2217 = propsDict.get(netRfc2217Key, u"")
				if not netRfc2217.lower().startswith("rfc2217://"):
					netRfc2217 = u"rfc2217://" + netRfc2217
				return netRfc2217
		except:
			return u""

	# Call through to pySerial's .Serial() constructor, but handle error exceptions by
	# logging them and returning None. No exceptions will be raised.
	def openSerial(self, ownerName, portUrl, baudrate, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=None, xonxoff=False, rtscts=False, writeTimeout=None, dsrdtr=False, interCharTimeout=None, errorLogFunc=None):
		if errorLogFunc is None:
			errorLogFunc = self.errorLog

		if not isinstance(portUrl, (str, unicode)) or len(portUrl) == 0:
			errorLogFunc(u"valid serial port not selected for \"%s\"" % (ownerName,))
			return None

		try:
			return serial.serial_for_url(portUrl, baudrate=baudrate, bytesize=bytesize, parity=parity, stopbits=stopbits, timeout=timeout, xonxoff=xonxoff, rtscts=rtscts, writeTimeout=writeTimeout, dsrdtr=dsrdtr, interCharTimeout=interCharTimeout)
		except Exception, exc:
			portUrl_lower = portUrl.lower()
			errorLogFunc(u"\"%s\" serial port open error: %s" % (ownerName, str(exc)))
			if "no 35" in str(exc):
				errorLogFunc(u"the specified serial port is used by another interface or device")
			elif portUrl_lower.startswith('rfc2217://') or portUrl_lower.startswith('socket://'):
				errorLogFunc(u"make sure remote serial server IP address and port number are correct")
			else:
				errorLogFunc(u"make sure the USB virtual serial port driver (ex: FTDI driver) is installed and correct port is selected")
			return None

