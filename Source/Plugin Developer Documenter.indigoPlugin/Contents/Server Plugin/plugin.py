#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# Plugin Developer Documenter by RogueProeliator <rp@rogueproeliator.com>
# 	Plugin to document the lifecycle that plugins go through and to demonstrate several
#	plugin features. This is meant for developers in order to demonstrate how to best
#	code and use the features provided by Indigo plugins.
#
#	Although many patterns exist for plugins, this example shows a few techniques
#	explicitly, including:
#		Using the background thread to keep the UI responsive
#		Utilizing a Queue to allow thread-safe communication with the background thread
#		Setting the hidden (to the user) 'address' property so that it shows in Indigo
#
#	IMPORTANT: NOT ALL THESE ROUTINES ARE NECESSARY. You likely only need a handful, please
#	see the notes with each routine, where appropriate. Nearly any routine may be left
#	out of the plugin entirely if you do not need to use it.
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////


#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
# the indigo module will be imported by the process hosting the plugin, you won't find this
# in your python directory and do not need to install/copy it
import indigo

# any standard python includes from 2.7 may be pulled in; in addition you may include 
# other modules in your plugin's bundle and import here.
import inspect
import logging
import os
import Queue
import sys
import time


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# Plugin
#	This is the main (and required) class for your plugin; it receives the events and
#	callbacks during normal processing.
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class Plugin(indigo.PluginBase):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor called once upon plugin class creation; setup the basic functionality
	# you need, create your variables, etc. Your devices are not created/ready here!
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		# ALWAYS call the base classes initializer so that the plugin is properly setup
		super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

		# you may do whatever you want to here with your variables; in this example we do not
		# need many, but you may wish to create a dictionary of indigo devices, create extra
		# settings, keep track of states, etc.
		self.logMethodParams = pluginPrefs.get("logMethodParams", False)
		
		# if the plugin defines Events to send, create a data store for them now so
		# that we can later trigger when necessary; this is not very common
		self.indigoEvents = dict()
		
		# this plugin uses a Queue to communicate with the background thread, passing actions
		# to it via this Queue. If your needs require, switch this to a PriorityQueue and
		# retrieval of items will be the lowest value specified via a sort of the entries:
		#	sorted(list(entries))[0]. The standard use is for each entry to be of the form:
		#	(priority_number, data).  Here we are just using a standard queue so only the
		# data element will be used. you must have this line at the top of the file:
		# import Queue
		self.commandQueue = Queue.Queue()
		
		# Indigo Plugins use standard Python based logging and provide a default instance
		# available to the plugin via the self.logger property
		# Examples (all standard Python logging calls):
		#	self.logger.debug(u'My debug message')
		#	self.logger.info(u'My informational message')
		#	self.logger.warn(u'Warn the user!')
		#
		# Indigo includes a new logging level called THREADDEBUG (logger level 5) that,
		# by default, logs to a plugin-specific file that is not normally sent to the
		# Indigo Log:
		self.indigo_log_handler.setLevel(logging.DEBUG)
		self.logger.threaddebug(u'A ton of logging information here that might be used for debugging by the developer!')
		self.debugLogWithLineNum(u'Called __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     ("' + pluginId + u'", "' + pluginDisplayName + u'", "' + pluginVersion + u'", ' + unicode(pluginPrefs) + u')')

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Destructor... normally need not do anything here...
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __del__(self):
		indigo.PluginBase.__del__(self)
		
		
	# ************************************************************************************
	# ************************************************************************************
	# *** CONFIGURATION-RELATED METHODS
	# ************************************************************************************
	# ************************************************************************************
	#/////////////////////////////////////////////////////////////////////////////////////
	# Plugin Configuration / Dialog Methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the XML for the PluginConfig.xml by default; you probably don't
	# want to use this unless you have a need to customize the XML (again, uncommon)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getPrefsConfigUiXml(self):
		self.debugLogWithLineNum(u'Called getPrefsConfigUiXml(self):')
		return super(Plugin, self).getPrefsConfigUiXml()

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the UI values for the configuration dialog; the default is to
	# simply return the self.pluginPrefs dictionary. It can be used to dynamically set
	# defaults at run time
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getPrefsConfigUiValues(self):
		self.debugLogWithLineNum(u'Called getPrefsConfigUiValues(self):')

		# example for customizing or setting default values...
		# valuesDict = self.pluginPrefs
		# errorMsgDict = indigo.Dict()
		# if not u'myProperty' in valuesDict:
		#	valuesDict[u'myProperty'] = u''
		# return (valuesDict, errorMsgDict)

		# returning the default handler as if this plugin had not overridden the routine
		return super(Plugin, self).getPrefsConfigUiValues()

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called in order to validate the inputs within the plugin config
	# dialog box. Return is a (True|False = isOk, valuesDict = values to save, errorMsgDict
	# = errors to display (if necessary))
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validatePrefsConfigUi(self, valuesDict):
		self.debugLogWithLineNum(u'Called validatePrefsConfigUi(self, valuesDict):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u')')

		# possible to do real validation and return an error if it fails, such as:		
		#errorMsgDict = indigo.Dict()
		#errorMsgDict[u"requiredFieldChk"] = u"You must check this box to continue"
		#return (False, valuesDict, errorMsgDict)
		
		# if no errors, return True and the values as a tuple
		return (True, valuesDict)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called once the user has exited the preferences dialog
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		self.debugLogWithLineNum(u'Called closedPrefsConfigUi(self, valuesDict, userCancelled):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u', ' + unicode(userCancelled) + ')')
			
		# if the user saved his/her preferences, update our member variables now
		if userCancelled == False:
			self.logMethodParams = valuesDict.get("logMethodParams", False)
			if self.pluginPrefs.get("registerForDevicesChanges", False) == True:
				indigo.devices.subscribeToChanges()
			if self.pluginPrefs.get("registerForVariableChanges", False) == True:
				indigo.variables.subscribeToChanges()
			if self.pluginPrefs.get("registerForActionGroupChanges", False) == True:
				indigo.actionGroups.subscribeToChanges()
			if self.pluginPrefs.get("registerForControlPageChanges", False) == True:
				indigo.controlPages.subscribeToChanges()
			if self.pluginPrefs.get("registerForScheduleChanges", False) == True:
				indigo.schedules.subscribeToChanges()
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Menu Item Configuration
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the menu items for the plugin; you normally don't need to
	# override this as the base class returns the menu items from the MenuItems.xml file
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getMenuItemsList(self):
		self.debugLogWithLineNum(u'Called getMenuItemsList(self):')
		return super(Plugin, self).getMenuItemsList()

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the configuration XML for the given menu item; normally this is
	# pulled from the MenuItems.xml file definition and you need not override it
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getMenuActionConfigUiXml(self, menuId):
		self.debugLogWithLineNum(u'Called getMenuActionConfigUiXml(self, menuId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(menuId) + u')')

		if menuId == u'dynamicUIDemonstration':
			self.logger.debug(u'Providing dynamic ConfigUI for menu item')
			customConfigUI = u'<?xml version="1.0" encoding="UTF-8"?><ConfigUI><Field id="example" type="label"><Label>This UI was dynamically created, not read through the MenuItems.xml file in the plugin.</Label></Field></ConfigUI>'
			self.logger.info(customConfigUI)
			return customConfigUI
		else:
			self.logger.info(super(Plugin, self).getMenuActionConfigUiXml(menuId))
			return super(Plugin, self).getMenuActionConfigUiXml(menuId)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the initial values for the menu action config dialog, if you
	# need to set them prior to the GUI showing
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getMenuActionConfigUiValues(self, menuId):
		self.debugLogWithLineNum(u'Called getMenuActionConfigUiValues(self, menuId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(menuId) + u')')
		valuesDict = indigo.Dict()
		errorMsgDict = indigo.Dict()
		return (valuesDict, errorMsgDict)
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Devices Configuration
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the dictionary of device types for the plugin; you should not
	# need to override this unless perhaps creating device types at runtime (uncommon)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDevicesDict(self):
		self.debugLogWithLineNum(u'Called getDevicesDict(self):')
		return super(Plugin, self).getDevicesDict()

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns a list of state definitions for the device; the default is to
	# return the list of states as defined for the device in the Devices.xml file
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceStateList(self, dev):
		self.debugLogWithLineNum(u'Called getDeviceStateList(self, dev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(dev) + u')')
		return super(Plugin, self).getDeviceStateList(dev)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the state that should be used in the "State" column of the
	# client; by default it pulls the ID from the Devices.xml UiDisplayStateId node
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceDisplayStateId(self, dev):
		self.debugLogWithLineNum(u'Called getDeviceDisplayStateId(self, dev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(dev) + u')')
		return super(Plugin, self).getDeviceDisplayStateId(dev)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Returns the class name for the device type provided; default is to return the "Type"
	# property from the device type dictionary (self.devicesTypeDict[typeId][u"Type"])
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceTypeClassName(self, typeId):
		self.debugLogWithLineNum(u'Called getDeviceTypeClassName(self, typeId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(typeId) + u')')
		return super(Plugin, self).getDeviceTypeClassName(typeId)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called in order to obtain the XML to be used for the device config
	# UI dialog; normally the base class simply returns the ConfigUI from Devices.xml
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceConfigUiXml(self, typeId, devId):
		self.debugLogWithLineNum(u'Called getDeviceConfigUiXml(self, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(typeId) + u', ' + unicode(devId) + u')')
		return super(Plugin, self).getDeviceConfigUiXml(typeId, devId)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the UI values for the device configuration screen prior to it
	# being shown to the user; it is sometimes used to setup default values at runtime
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
		self.debugLogWithLineNum(u'Called getDeviceConfigUiValues(self, pluginProps, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(pluginProps) + u', ' + unicode(typeId) + u', ' + unicode(devId) + u')')
		return super(Plugin, self).getDeviceConfigUiValues(pluginProps, typeId, devId)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will validate the device configuration dialog when the user attempts
	# to save the data
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateDeviceConfigUi(self, valuesDict, typeId, devId):
		self.debugLogWithLineNum(u'Called validateDeviceConfigUi(self, valuesDict, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u', ' + unicode(typeId) + u', ' + unicode(devId) + u')')
			
		# we may also change the values, here we will set the value of the address
		# to the time
		valuesDict['address'] = time.strftime('%l:%M%p')
		
		if valuesDict.get('requiredField', False) == False:
			errorMsgDict = indigo.Dict()
			errorMsgDict[u"requiredField"] = u"You must check this box to continue"
			return (False, valuesDict, errorMsgDict)
		else:
			return (True, valuesDict)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called whenever the user has closed the device config dialog
	# either by save or cancel
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
		self.debugLogWithLineNum(u'Called closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u', ' + unicode(userCancelled) + ', ' + unicode(typeId) + u', ' + unicode(devId) + u')')
		return
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called in order to determine if a communication-related
	# property of the device has changed; such as serial port, IP, etc. This allows you
	# to override (return True/False) if the device must stop/restart communication after
	# a property change. If True is returned the deviceStopComm / deviceStartComm are
	# called to pick up the change. By default ALL properties are considered comm related!
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def didDeviceCommPropertyChange(self, origDev, newDev):
		self.debugLogWithLineNum(u'Called didDeviceCommPropertyChange(self, origDev, newDev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(origDev) + u', ' + unicode(newDev) + u')')
		return super(Plugin, self).didDeviceCommPropertyChange(origDev, newDev)
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Device Factory Configuration Routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called in order to obtain the XML to be used for the factory
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceFactoryUiXml(self):
		self.debugLogWithLineNum(u'Called getDeviceFactoryUiXml(self):')
		return super(Plugin, self).getDeviceFactoryUiXml()
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the UI values for the device factory screen prior to it
	# being shown to the user
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceFactoryUiValues(self, devIdList):
		self.debugLogWithLineNum(u'Called getDeviceFactoryUiValues(self, devIdList):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(devIdList) + ')')
		return super(Plugin, self).getDeviceFactoryUiValues(devIdList)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will validate the device factory dialog when the user attempts
	# to save the data
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateDeviceFactoryUi(self, valuesDict, devIdList):
		self.debugLogWithLineNum(u'Called validateDeviceFactoryUi(self, valuesDict, devIdList):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u', ' + unicode(devIdList) + ')')
		# errorMsgDict = indigo.Dict()
		# errorMsgDict[u"someUiFieldId"] = u"sorry but you MUST check this checkbox!"
		# return (False, valuesDict, errorMsgDict)
		return (True, valuesDict)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called whenever the user has closed the device factory dialog
	# either by save or cancel
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def closedDeviceFactoryUi(self, valuesDict, userCancelled, devIdList):
		self.debugLogWithLineNum(u'Called closedDeviceFactoryUi(self, valuesDict, userCancelled, devIdList):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u', ' + unicode(userCancelled) + u', ' + unicode(devIdList) + u')')
		return
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Actions Configuration
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the actions for the plugin; you normally don't need to
	# override this as the base class returns the actions from the Actions.xml file
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getActionsDict(self):
		self.debugLogWithLineNum(u'Called getActionsDict(self):')
		return super(Plugin, self).getActionsDict()
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine obtains the callback method to execute when the action executes; it
	# normally just returns the action callback specified in the Actions.xml file
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getActionCallbackMethod(self, typeId):
		self.debugLogWithLineNum(u'Called getActionCallbackMethod(self, typeId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(typeId) + u')')
		return super(Plugin, self).getActionCallbackMethod(typeId)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the configuration XML for the given action; normally this is
	# pulled from the Actions.xml file definition and you need not override it
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getActionConfigUiXml(self, typeId, devId):
		self.debugLogWithLineNum(u'Called getActionConfigUiXml(self, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(typeId) + u', ' + unicode(devId) + u')')
		return super(Plugin, self).getActionConfigUiXml(typeId, devId)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the UI values for the action configuration screen prior to it
	# being shown to the user
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getActionConfigUiValues(self, pluginProps, typeId, devId):
		self.debugLogWithLineNum(u'Called getActionConfigUiValues(self, pluginProps, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(pluginProps) + u', ' + unicode(typeId) + u', ' + unicode(devId) + u')')
		return super(Plugin, self).getActionConfigUiValues(pluginProps, typeId, devId)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will validate the action config dialog when the user attempts
	# to save the data
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateActionConfigUi(self, valuesDict, typeId, devId):
		self.debugLogWithLineNum(u'Called validateActionConfigUi(self, valuesDict, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u', ' + unicode(typeId) + u', ' + unicode(devId) + u')')
		
		# If validation fails, return False and an error dictionary such as:
		# errorMsgDict = indigo.Dict()
		# errorMsgDict[u"someUiFieldId"] = u"sorry but you MUST check this checkbox!"
		# return (False, valuesDict, errorMsgDict)
		return (True, valuesDict)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called whenever the user has closed the action config dialog
	# either by save or cancel
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def closedActionConfigUi(self, valuesDict, userCancelled, typeId, devId):
		self.debugLogWithLineNum(u'Called closedActionConfigUi(self, valuesDict, userCancelled, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(valuesDict) + u', ' + unicode(userCancelled) + ', ' + unicode(typeId) + u', ' + unicode(devId) + u')')
		return

	
	# ************************************************************************************
	# ************************************************************************************
	# *** STANDARD OPERATION LIFECYCLE METHODS
	# ************************************************************************************
	# ************************************************************************************
	#/////////////////////////////////////////////////////////////////////////////////////
	# Indigo Plugin Control Methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# startup is called by Indigo whenever the plugin is first starting up (by a restart
	# of Indigo server or the plugin or an update
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def startup(self):
		self.debugLogWithLineNum(u'Called startup(self):')
		if self.pluginPrefs.get("registerForDevicesChanges", False) == True:
			indigo.devices.subscribeToChanges()
		if self.pluginPrefs.get("registerForVariableChanges", False) == True:
			indigo.variables.subscribeToChanges()
		if self.pluginPrefs.get("registerForActionGroupChanges", False) == True:
			indigo.actionGroups.subscribeToChanges()
		if self.pluginPrefs.get("registerForControlPageChanges", False) == True:
			indigo.controlPages.subscribeToChanges()
		if self.pluginPrefs.get("registerForScheduleChanges", False) == True:
			indigo.schedules.subscribeToChanges()
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will run a concurrent processing thread used at the plugin (not
	# device) level to keep the GUI clear of blocking calls
	#
	# NOTE: This represents just one implementation pattern/example utilizing a queue to
	# handle all plugin commands. Your plugin may need individual threads per device, no
	# background thread at all, or a combination of the two.
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def runConcurrentThread(self):
		try:
			# this will create an infinite loop which exits via exception or you could
			# implement your own method/scheme to exit
			while True:
				# here you can poll for information, await commands send in via a queue
				# from callbacks to your plugin or whatever your particular plugin needs.
				# we will process items found in the command queue
				while not self.commandQueue.empty():
					lenQueue = self.commandQueue.qsize()
					self.debugLogWithLineNum(u'Command queue has ' + unicode(lenQueue) + ' command(s) waiting')
					
					# you get the next item in the queue via a get() call
					command = self.commandQueue.get()
					
					# here you would process the command which could be whatever you put in the queue
					# via your actions... this might be a tuple, a class, or anything. here we are
					# just passing in a tuple... the command and a parameter
					self.debugLogWithLineNum(u'Command executed: ' + command[0])
					
					if command[0] == "incrementDeviceState":
						# we added the device ID as the second parameter of the tuple...
						deviceForAction = indigo.devices[command[1]]
						currentValue = int(deviceForAction.states.get('exampleNumberState', '0'))
						currentValue += 1
						deviceForAction.updateStateOnServer(key='exampleNumberState', value=currentValue)
						
						# you may want to sleep after certain commands - this would be specific to your plugin
						# and possibly command... for instance, after a power-on command, might want to sleep
						# a time to be sure the device powers up
						self.sleep(0.4)
						
					elif command[0] == "decrementDeviceState":
						# we added the device ID as the second parameter of the tuple...
						deviceForAction = indigo.devices[command[1]]
						currentValue = int(deviceForAction.states.get('exampleNumberState', '0'))
						currentValue -= 1
						deviceForAction.updateStateOnServer(key='exampleNumberState', value=currentValue)
		
						# each command might have a different (or no) sleep requirement...
						self.sleep(0.2)
					
					# complete the dequeuing of the command, allowing the next
					# command in queue to rise to the top
					self.commandQueue.task_done()
				
				# the queue is now empty... you need to sleep on each iteration lest you eat up all
				# of the CPU cycles on the server! this custom sleep command may be interrupted and
				# is provided on the plugin base class; parameter is in seconds. If you want to
				# explore queueing up commands to see how it works "stacked up", increase this to, say,
				# 10 seconds
				self.sleep(0.5)
				
		except self.StopThread:
			# if needed you could do any cleanup here, or could exit via another flag
			# or command from your plugin
			pass
		except:
			# this fall through will catch any other error that you were not expecting...
			# you may want to set the error state for the device(s) via a call to:
			#    [device].setErrorStateOnServer("Error")
			# you may also wish to schedule a re-connection attempt, if appropriate for the device
			self.exceptionLog()

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# shutdown is called by Indigo whenever the entire plugin is being shut down from
	# being disabled, during an update process or if the server is being shut down.
	#
	# NOTE: This should return very quickly as it indicates the server is attempting to
	# stop the plugin and it may get killed if it takes too long to exit
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def shutdown(self):
		self.debugLogWithLineNum(u'Called shutdown(self):')


	#/////////////////////////////////////////////////////////////////////////////////////
	# Indigo Device Lifecycle Callback Routines
	#	You may receive notifications of creation/updates/deletion of ALL devices in the
	#	system (not just your own) by calling:
	#		indigo.devices.subscribeToChanges()
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a device is created; if you override it, be sure to
	# call the base class processing! The base class will call the deviceStartComm if
	# appropriate, you don't need to do that yourself
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def deviceCreated(self, dev):
		self.debugLogWithLineNum(u'Called deviceCreated(self, dev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(dev) + u')')
		super(Plugin, self).deviceCreated(dev)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the plugin should be connecting / communicating with
	# the physical device... here is where you would begin tracking the device as well
	# if keeping a reference to the device or spawning a new communication thread for each
	# individual device
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def deviceStartComm(self, dev):
		self.debugLogWithLineNum(u'Called deviceStartComm(self, dev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(dev) + u')')
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a device has been updated; if you override it, be
	# sure to call the base class processing.
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def deviceUpdated(self, origDev, newDev):
		self.debugLogWithLineNum(u'Called deviceUpdated(self, origDev, newDev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(origDev) + u', ' + unicode(newDev) + u')')
		super(Plugin, self).deviceUpdated(origDev, newDev)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the plugin should cease communicating with the
	# hardware/software, breaking the connection
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def deviceStopComm(self, dev):
		self.debugLogWithLineNum(u'Called deviceStopComm(self, dev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(dev) + u')')
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a device has been deleted... be sure to call the
	# base class routine if you override or else you may break part of the lifecycle of
	# properly shutting down the device
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def deviceDeleted(self, dev):
		self.debugLogWithLineNum(u'Called deviceDeleted(self, dev):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'     (' + unicode(dev) + u')')
		super(Plugin, self).deviceDeleted(dev)
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Indigo Events Processing
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a trigger is created; if you override it, be sure to
	# call the base class processing... this is called for all triggers, not just those
	# associated with your plugin; you can check the ID if looking for a particular one
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerCreated(self, trigger):
		self.debugLogWithLineNum(u'Called triggerCreated(self, trigger):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(trigger) + u')')
		super(Plugin, self).triggerCreated(trigger)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the server is starting an event / trigger setup
	# by the user
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerStartProcessing(self, trigger):
		self.debugLogWithLineNum(u'Called triggerStartProcessing(self, trigger):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(trigger) + u')')
		
		# store the trigger in a member variable so that it may be called back whenever
		# our triggering action occurs
		triggerType = trigger.pluginTypeId
		if not (triggerType in self.indigoEvents):
			self.indigoEvents[triggerType] = dict()
		self.indigoEvents[triggerType][trigger.id] = trigger
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a trigger is updated; if you override it, be sure to
	# call the base class processing... this is called for all triggers, not just those
	# associated with your plugin; you can check the ID(s) if looking for a particular one
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerUpdated(self, origTrigger, newTrigger):
		self.debugLogWithLineNum(u'Called triggerUpdated(self, origTrigger, newTrigger):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(origTrigger) + u', ' + unicode(newTrigger) + u')')
		super(Plugin, self).triggerUpdated(origTrigger, newTrigger)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the server is un-registering a trigger
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerStopProcessing(self, trigger):
		self.debugLogWithLineNum(u'Called triggerStopProcessing(self, trigger):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(trigger) + u')')
		
		# if the trigger exists within our list, go ahead and delete it out now
		triggerType = trigger.pluginTypeId
		if triggerType in self.indigoEvents:
			if trigger.id in self.indigoEvents[triggerType]:
				del self.indigoEvents[triggerType][trigger.id]
				
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a trigger is deleted; if you override it, be sure to
	# call the base class processing... this is called for all triggers, not just those
	# associated with your plugin; you can check the ID if looking for a particular one
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerDeleted(self, trigger):
		self.debugLogWithLineNum(u'Called triggerDeleted(self, trigger):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(trigger) + u')')
		super(Plugin, self).triggerDeleted(trigger)
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# PLUGIN-DEFINED CALLBACK ROUTINES
	#	These routines are all examples of callbacks that the plugin has defined and set
	#	as callbacks for menu items and buttons on config forms, actions, menu items, etc.
	#	Each plugin will be different, these are just examples to show the lifecycle calls
	#	and examples.
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This callback originates from the menu item without a UI
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def customMenuItem1Executed(self):
		self.debugLogWithLineNum(u'Called customMenuItem1Executed(self):')
		self.commandQueue.put((u'Queued action from customMenuItem1Executed', 0))
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This callback originates from the menu item that should trigger the custom event
	# defined by the plugin
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerEventFromMenu(self):
		self.debugLogWithLineNum(u'Called triggerEventFromMenu(self):')
		if 'samplePluginEvent' in self.indigoEvents:
			for trigger in self.indigoEvents['samplePluginEvent'].values():
				indigo.trigger.execute(trigger)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This callback originates from the menu item with a UI
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def customMenuItem2Executed(self, valuesDict, typeId):
		self.debugLogWithLineNum(u'Called customMenuItem2Executed(self, valuesDict, typeId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(valuesDict) + u', ' + unicode(typeId) + u')')
			
		# you may return an error dictionary here like other UI validation routines
		# errorsDict = indigo.Dict()
		# errorsDict['somefield'] = 'Issue found'
		# return (False, valuesDict, errorsDict)
		
		# queue up an action as a demonstration
		self.commandQueue.put((u'Queued action from customMenuItem2Executed', 0))
		
		return (True, valuesDict)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is set to handle the Add to Counter action via the Actions.xml
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def changeCustomDeviceCounterState(self, action):
		self.debugLogWithLineNum(u'Called changeCustomDeviceCounterState(self, action):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(action) + u')')
		self.commandQueue.put((action.pluginTypeId, action.deviceId))
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Called whenever the user has submitted a custom message to be broadcast to all
	# subscribing plugins
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def sendIntraPluginBroadcast(self, valuesDict, typeId):
		self.debugLogWithLineNum(u'Called sendIntraPluginBroadcast(self, valuesDict, typeId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(valuesDict) + u', ' + unicode(typeId) + u')')

		indigo.server.broadcastToSubscribers(valuesDict.get(u'message', u''))

		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is set to handle the Set Custom Device State action via the Actions.xml
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def setCustomDeviceState(self, action):
		self.debugLogWithLineNum(u'Called setCustomDeviceState(self, action):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(action) + u')')
		deviceForAction = indigo.devices[action.deviceId]
		if action.props.get('addSymbolToState', False) == True:
			deviceForAction.updateStateOnServer(key='exampleDisplayState', value=action.props.get('newStateValue', ''), uiValue=action.props.get('newStateValue', '') + u'°')
		else:
			deviceForAction.updateStateOnServer(key='exampleDisplayState', value=action.props.get('newStateValue', ''))
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called when the user clicks the button on the device configuration
	# dialog
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def customDeviceConfigCallback(self, valuesDict, typeId, devId):
		self.debugLogWithLineNum(u'Called customDeviceConfigCallback(self, valuesDict, typeId, devId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(valuesDict) + u', ' + unicode(typeId) + u', ' + unicode(devId) + u')')
		return valuesDict
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the dynamic list on the config UI screen needs
	# updating
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getCustomDeviceConfigMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
		self.debugLogWithLineNum(u'Called getCustomDeviceConfigMenu(self, filter, valuesDict, typeId, targetId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(filter) + u', ' + unicode(valuesDict) + u', ' + unicode(typeId) + u', ' + unicode(targetId) + u')')
		optionsArray = [("option1", "First Option"),("option2","Second Option")]
		return optionsArray
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the dynamic list on the config UI screen needs
	# updating; this list updates on any round trip to the server
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getCustomDeviceConfigReloadingMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
		self.debugLogWithLineNum(u'Called getCustomDeviceConfigReloadingMenu(self, filter, valuesDict, typeId, targetId):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(filter) + u', ' + unicode(valuesDict) + u', ' + unicode(typeId) + u', ' + unicode(targetId) + u')')
		optionsArray = [("option3", "Dyna First Option"),("option4","Dyna Second Option")]
		return optionsArray
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Schedule Lifecycle Events
	#	These routines are called to allow the plugin to react, if necessary, to any
	#	schedule lifecycle events; they will not be associated with this plugin and 
	#	generally are not necessary to have in your plugin
	#
	#	To receive these callbacks, your plugin will need to call:
	#		indigo.schedules.subscribeToChanges()
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a schedule has been created
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def scheduleCreated(self, schedule):
		self.debugLogWithLineNum(u'Called scheduleCreated(self, schedule):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(schedule) + u')')
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a schedule has been updated
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def scheduleUpdated(self, origSchedule, newSchedule):
		self.debugLogWithLineNum(u'Called scheduleUpdated(self, origSchedule, newSchedule):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(origSchedule) + u', ' + unicode(newSchedule) + u')')

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a schedule has been deleted
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def scheduleDeleted(self, schedule):
		self.debugLogWithLineNum(u'Called scheduleDeleted(self, schedule):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(schedule) + u')')

	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Action Group Lifecycle Events
	# These routines are called to allow the plugin to react, if necessary, to any
	#	action group lifecycle events; they will not be associated with this plugin and 
	#	generally are not necessary to have in your plugin
	#
	#	To receive these callbacks your plugin will need to call:
	#		indigo.actionGroups.subscribeToChanges()
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever an action group has been created
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def actionGroupCreated(self, group):
		self.debugLogWithLineNum(u'Called actionGroupCreated(self, group):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(group) + u')')
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever an action group has been updated
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def actionGroupUpdated(self, origGroup, newGroup):
		self.debugLogWithLineNum(u'Called actionGroupUpdated(self, origGroup, newGroup):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(origGroup) + u', ' + unicode(newGroup) + u')')

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever an action group has been deleted
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def actionGroupDeleted(self, group):
		self.debugLogWithLineNum(u'Called actionGroupDeleted(self, group):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(group) + u')')

	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Control Page Lifecycle Events
	#	These routines are called to allow the plugin to react, if necessary, to any
	#	control page lifecycle events; they will not be associated with this plugin and 
	#	generally are not necessary to have in your plugin 
	#
	#	To receive these callbacks your plugin will need to call:
	#		indigo.controlPages.subscribeToChanges()
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a control page has been created
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def controlPageCreated(self, page):
		self.debugLogWithLineNum(u'Called controlPageCreated(self, page):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(page) + u')')
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a control page has been updated
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def controlPageUpdated(self, origPage, newPage):
		self.debugLogWithLineNum(u'Called controlPageUpdated(self, origPage, newPage):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(origPage) + u', ' + unicode(newPage) + u')')

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever a control page has been deleted
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def controlPageDeleted(self, page):
		self.debugLogWithLineNum(u'Called controlPageDeleted(self, page):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(page) + u')')

	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Indigo Variables Lifecycle Events
	#	These routines are called to allow the plugin to react, if necessary, to any
	#	Indigo variable lifecycle events; they will not be associated with this plugin and 
	#	generally are not necessary to have in your plugin 
	#
	#	To receive these callbacks your plugin will need to call:
	#		indigo.variables.subscribeToChanges()
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever an Indigo variable has been created
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def variableCreated(self, var):
		self.debugLogWithLineNum(u'Called variableCreated(self, var):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(var) + u')')

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever an Indigo variable has been updated
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def variableUpdated(self, origVar, newVar):
		self.debugLogWithLineNum(u'Called variableUpdated(self, origVar, newVar):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(origVar) + u', ' + unicode(newVar) + u')')
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever an Indigo variable has been deleted
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def variableDeleted(self, var):
		self.debugLogWithLineNum(u'Called variableDeleted(self, var):')
		if self.logMethodParams == True:
			self.debugLogWithLineNum(u'   (' + unicode(var) + u')')
			

	#/////////////////////////////////////////////////////////////////////////////////////
	# Broadcast (Publish) and Subscribe
	#	These routines allow your program to "publish" information that may be consumed
	#	by other programs which subscribe to broadcasts (or allow you to be the consumer!)
	# /////////////////////////////////////////////////////////////////////////////////////

		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Utility Routines
	#/////////////////////////////////////////////////////////////////////////////////////
	def debugLogWithLineNum(self, message):
		self.logger.debug(u'[' + unicode(inspect.currentframe().f_back.f_lineno) + '] ' + message)
