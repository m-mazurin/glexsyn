#!/usr/bin/env python3

import sys
import datetime
import dateutil.parser

from PyQt5 import QtWidgets
from PyQt5 import QtGui
from PyQt5.QtCore import QThread

import labstep

import glx_design

class loginThread(QThread):
	"""
	Thread for auth procedure, write User in local variable

	"""
	user = None
	def __init__(self):
		QThread.__init__(self)

	def __del__(self):
		self.wait()

	def run(self):
		try:
			user = ""
			key = ""
			with open("key.cfg","r") as kf:
				user = kf.readline().rstrip("\n")
				key = kf.readline().rstrip("\n")
			self.user = labstep.authenticate(user,key)
			print(self.user.name)
		except Exception as ex:
			self.user = None
			print(ex)

class getWorkspacesThread(QThread):
	"""
	Thread for getting workspaces, write workspaces instance in local varialbe 'wsps'

	"""
	def __init__(self, user):
		QThread.__init__(self)
		self.user = user

	def __del__(self):
		self.wait()

	def run(self):
		self.wsps = self.user.getWorkspaces()

class getExperimentsThread(QThread):
	"""
	Thread for getting experiments, write experiments instance in local variable 'exps'

	"""
	def __init__(self, wsp, tagId):
		QThread.__init__(self)
		self.wsp = wsp
		self.tagId = tagId

	def __del__(self):
		self.wait()

	def run(self):
		#self.expsTags = []
		self.exps = self.wsp.getExperiments(count=1000) if self.tagId == -1 else self.wsp.getExperiments(count=1000,tag_id=self.tagId)
		#for exp in self.exps:
		#	self.expsTags.append(exp.getTags())

class getSpecExperimentThread(QThread):
	"""
	Thread for getting specific experiment, save experiment data to local variable 'exp'

	"""
	def __init__(self, user, expId):
		QThread.__init__(self)
		self.user = user
		self.expId = expId

	def __del__(self):
		self.wait()

	def run(self):
		self.exp = self.user.getExperiment(self.expId)

class getExperimentTagsThread(QThread):
	"""
	Thread for getting specific experiment's tags, save data to local var 'tags'

	"""
	def __init__(self, exp):
		QThread.__init__(self)
		self.exp = exp

	def __del__(self):
		self.wait()

	def run(self):
		self.tags = self.exp.getTags()

class saveOverviewThread(QThread):
	"""
	Thread for send changes in overview to labstep server

	"""
	def __init__(self, exp, expTags, title, body, plainTags):
		QThread.__init__(self)
		self.exp = exp
		self.title = title
		self.body = body

		self.expTags = expTags
		self.plainTags = plainTags

	def __del__(self):
		self.wait()

	def run(self):
		self.exp.edit(name=self.title,description=self.body)

		#if there are new tags - call addTag
		existedTagsNames = [t.name for t in self.expTags]
		if not self.plainTags:
			return
		editedTagsNames = self.plainTags.split(";")
		for t in editedTagsNames:
			if t not in existedTagsNames:
				self.exp.addTag(t)

class glx_designApp(QtWidgets.QMainWindow, glx_design.Ui_MainWindow):
	default_wsp_index = 0

	#Local session variables
	#==========================
	#There will be user data
	user = None
	#List of workspaces
	wsps = None
	#Current selected workspace
	curWspIndex = -1
	curWsp = None
	#Loaded experiments and their tags
	exps = None
	#Current experiment to view and edit
	curExp = None
	curExpIndex = -1
	oldExpItem = None
	#Whole user's tags
	userTags = None
	#Current experiment's tags
	curExpTags = None
	#Store changes flag
	isChanges = False
	#Current filter tag id
	curFilterTagId = -1
	#Current filter index in !!! userTags array !!!
	curFilterTagIndex = -1
	#==========================

	def __init__(self):
		super().__init__()
		self.setupUi(self)

		self.expTree.setHeaderLabels(["Experiments"])

		self.wspComboBox.currentIndexChanged.connect(self.changeWorkspace)
		self.expTree.itemSelectionChanged.connect(self.selectExperiment)
		self.tagComboBox.currentIndexChanged.connect(self.filterExperiments)

		self.descriptionEdit.cursorPositionChanged.connect(self.onDescSelected)
		self.boldButton.clicked.connect(self.boldClicked)
		self.italicButton.clicked.connect(self.italicClicked)
		self.underlineButton.clicked.connect(self.underlineClicked)
		self.superscriptButton.clicked.connect(self.superscriptClicked)
		self.subscriptButton.clicked.connect(self.subscriptClicked)
		self.saveOverviewButton.clicked.connect(self.saveOverviewClicked)

		#Editing event to unlock save button
		self.descriptionEdit.textChanged.connect(self.unblockSave)
		self.titleEdit.textChanged.connect(self.unblockSave)
		self.tagsEdit.textChanged.connect(self.unblockSave)

	# ============================================
	# Filtering experiments by tags logic
	# ============================================
	def filterExperiments(self, index):
		#need confirm if there are changes
		if self.isChanges:
			if not self.confirmLeaving():
				self.tagComboBox.blockSignals(True)
				self.tagComboBox.setCurrentIndex(self.curFilterTagIndex+1)
				self.tagComboBox.blockSignals(False)
				return
		#zero-index always pointer to "show all" item
		self.curFilterTagId = -1 if index == 0 else self.userTags[index-1].id 
		self.curFilterTagIndex = index-1

		self.getExperiments_thread = getExperimentsThread(self.curWsp, self.curFilterTagId)
		self.getExperiments_thread.started.connect(lambda: self.blockUi(True, "Getting experiments..."))
		self.getExperiments_thread.finished.connect(self.gotExperiments)
		self.getExperiments_thread.start()


	# ============================================
	# Tracking changes and confirmation logic
	# ============================================
	def unblockSave(self):
		if not self.curExp.permissions['edit']:
			return
		self.isChanges = True
		self.saveOverviewButton.setDisabled(False)

	def confirmLeaving(self):
		result = QtWidgets.QMessageBox.question(self,"Fields has been changed","Do you want to leave editing? Unsaved changes will be lost!")
		if result == QtWidgets.QMessageBox.No:
			return False
		else:
			return True
	# Overload close event to confirm quit if there are changes
	def closeEvent(self, event):
		if self.isChanges and not self.confirmLeaving():
			event.ignore()
		else:
			event.accept()
	# ============================================	
	# RTF-editor buttons logic
	# ============================================
	def boldClicked(self, checked):
		fmt = QtGui.QTextCharFormat()
		fmt.setFontWeight(QtGui.QFont.Bold if checked else QtGui.QFont.Normal)
		self.descriptionEdit.mergeCurrentCharFormat(fmt)

	def italicClicked(self, checked):
		fmt = QtGui.QTextCharFormat()
		fmt.setFontItalic(checked)
		self.descriptionEdit.mergeCurrentCharFormat(fmt)

	def underlineClicked(self, checked):
		fmt = QtGui.QTextCharFormat()
		fmt.setFontUnderline(checked)
		self.descriptionEdit.mergeCurrentCharFormat(fmt)

	def superscriptClicked(self, checked):
		fmt = QtGui.QTextCharFormat()
		fmt.setVerticalAlignment(QtGui.QTextCharFormat.AlignSuperScript if checked else QtGui.QTextCharFormat.AlignNormal)
		self.descriptionEdit.mergeCurrentCharFormat(fmt)

	def subscriptClicked(self, checked):
		fmt = QtGui.QTextCharFormat()
		fmt.setVerticalAlignment(QtGui.QTextCharFormat.AlignSubScript if checked else QtGui.QTextCharFormat.AlignNormal)
		self.descriptionEdit.mergeCurrentCharFormat(fmt)
	# ============================================

	def onDescSelected(self):
		""" Edit format buttons when something selected in QTextEdit """
		fmt = self.descriptionEdit.currentCharFormat()
		#Check current format and set buttons checked
		self.boldButton.setChecked(fmt.fontWeight() == QtGui.QFont.Bold)

		self.italicButton.setChecked(fmt.fontItalic())
		self.underlineButton.setChecked(fmt.fontUnderline())

		self.superscriptButton.setChecked(fmt.verticalAlignment() == QtGui.QTextCharFormat.AlignSuperScript)
		self.subscriptButton.setChecked(fmt.verticalAlignment() == QtGui.QTextCharFormat.AlignSubScript)

	# ============================================
	# Saving overview logic
	# ============================================
	def saveOverviewClicked(self):
		""" Saving changes in overview """
		if self.curExp is None:
			return
		#print(self.descriptionEdit.toHtml())
		self.saveOverview_thread = saveOverviewThread(self.curExp,self.curExpTags,self.titleEdit.text(),self.descriptionEdit.toHtml(),self.tagsEdit.text())
		self.saveOverview_thread.started.connect(lambda: self.blockUi(True,"Saving to LabStep server..."))
		self.saveOverview_thread.finished.connect(self.overviewSaved)
		self.saveOverview_thread.start()

	def overviewSaved(self):
		self.blockUi(False, "Ready")
		#Update title in QTreeView
		self.expTree.topLevelItem(0).child(self.curExpIndex).setText(0,self.titleEdit.text())
		#Reload experiment?
		self.getSpecExperiment_thread = getSpecExperimentThread(self.user,self.curExp.id)
		self.getSpecExperiment_thread.started.connect(lambda: self.blockUi(True, "Reload experiment..."))
		self.getSpecExperiment_thread.finished.connect(self.gotSpecExperiment)
		self.getSpecExperiment_thread.start()
	# ============================================
	# Loading specific experiment logic + loading tags
	# ============================================
	def selectExperiment(self):
		"""
		Select experiment -> Load experiment in new thread -> Load tags in new thread -> Finalize

		"""
		#Get new selected item, if no selection - return
		if len(self.expTree.selectedItems()) == 0:
			return

		current = self.expTree.selectedItems()[0]
		#Check that current selected item is not top-level
		if current is not self.expTree.topLevelItem(0):
			#Check changes
			if self.isChanges:
				if not self.confirmLeaving():
					#DISABLE SIGNALS to avoid reselect
					self.expTree.blockSignals(True)
					#Set selection to OLD item
					current.setSelected(False)
					self.oldExpItem.setSelected(True)
					#ENABLE signals
					self.expTree.blockSignals(False)
					return
			#Store new selected item as old item
			self.oldExpItem = current
			#Get index to access
			index = self.expTree.topLevelItem(0).indexOfChild(current)
			self.curExpIndex = index
			#Get ID of this experiment
			expId = self.exps[index].id
			#Lock UI and start getting experiment
			self.getSpecExperiment_thread = getSpecExperimentThread(self.user,expId)
			self.getSpecExperiment_thread.started.connect(lambda: self.blockUi(True, "Getting \""+self.exps[index].name+"\"..."))
			self.getSpecExperiment_thread.finished.connect(self.gotSpecExperiment)
			self.getSpecExperiment_thread.start()
			

	def gotSpecExperiment(self):
		self.curExp = self.getSpecExperiment_thread.exp
		self.descriptionEdit.clear()
		self.descriptionEdit.setCurrentCharFormat(QtGui.QTextCharFormat())

		if self.curExp.description is not None:
			self.descriptionEdit.append(self.curExp.description)
			self.descriptionEdit.setTextCursor(QtGui.QTextCursor(self.descriptionEdit.document()))
			#print(self.curExp.description)
		if self.curExp.name is not None:
			self.titleEdit.setText(self.curExp.name)

		dt_up = self.LSDateStringToDatetime(self.curExp.updated_at)
		dt_created = self.LSDateStringToDatetime(self.curExp.created_at)
		dt_format = "%d %b, %Y %H:%M"
		self.updatedLabel.setText("Updated at: " + dt_up.strftime(dt_format))
		self.createdLabel.setText("Created at: " + dt_created.strftime(dt_format))

		#self.tagsEdit.setText(self.TagsToStr(self.expsTags[self.curExpIndex]))

		self.getExperimentTags_thread = getExperimentTagsThread(self.curExp)
		self.getExperimentTags_thread.started.connect(lambda: self.blockUi(True, "Getting tags..."))
		self.getExperimentTags_thread.finished.connect(self.gotExperimentTags)
		self.getExperimentTags_thread.start()

	def gotExperimentTags(self):
		self.curExpTags = self.getExperimentTags_thread.tags
		self.tagsEdit.setText(self.TagsToStr(self.curExpTags))
		#Reset changes' flag
		self.isChanges = False
		self.saveOverviewButton.setDisabled(True)
		#Unblock UI
		self.blockUi(False,"Ready")

	def TagsToStr(self, listOfTags):
		s = ""
		for t in listOfTags:
			s += t.name + ";"
		s = s.rstrip(';')
		return s

	# ============================================
	# Change and load workspace logic
	# ============================================
	def changeWorkspace(self,index):
		#after FIRST loaded worspace curWspIndex = -1, so that code will be ignored
		if index == self.curWspIndex:
			return

		if self.isChanges:
			if not self.confirmLeaving():
				self.wspComboBox.blockSignals(True)
				self.wspComboBox.setCurrentIndex(self.curWspIndex)
				self.wspComboBox.blockSignals(False)
				return

		self.curWsp = self.getWorkspaces_thread.wsps[index]
		self.curWspIndex = index

		self.ronlyCheckBox.setChecked(not self.curWsp.permissions['edit'])

		self.getExperiments_thread = getExperimentsThread(self.curWsp, self.curFilterTagId)
		self.getExperiments_thread.started.connect(lambda: self.blockUi(True, "Getting experiments..."))
		self.getExperiments_thread.finished.connect(self.gotExperiments)
		self.getExperiments_thread.start()

	def gotWorkspaces(self):
		""" Callback function, update combobox with workspaces """
		#Extract workspaces from thread
		self.wsps = self.getWorkspaces_thread.wsps
		self.curWsp = self.wsps[0]
		#Update combobox
		self.wspComboBox.clear()
		for wsp in self.wsps:
			self.wspComboBox.addItem(wsp.name)

	def gotExperiments(self):
		""" Callback function, update tree and unblock UI"""
		self.exps = self.getExperiments_thread.exps
		#self.expsTags = self.getExperiments_thread.expsTags
		#Update QtTreeWidget
		self.expTree.clear()

		headItem = QtWidgets.QTreeWidgetItem(None,[self.curWsp.name])
		expItems = [QtWidgets.QTreeWidgetItem(headItem,[e.name]) for e in self.exps]

		self.expTree.addTopLevelItem(headItem)
		headItem.setExpanded(True)
		#Finally, clear overview tab and unblock UI
		self.blockUi(False, str(len(self.exps)) + " experiments loaded!..")

		#Block tabs before specific experiment will be selected and reset changes flag
		self.isChanges = False
		self.tabWidget.setDisabled(True)

	def gotUserTags(self):
		self.userTags = self.getUserTags_thread.tags

		#block signals and fill combobox
		self.tagComboBox.blockSignals(True)
		self.tagComboBox.clear()
		self.tagComboBox.addItem("Show all")
		for t in self.userTags:
			self.tagComboBox.addItem(t.name)
		self.tagComboBox.blockSignals(False)

	# ============================================

	def loggedIn(self):
		""" Callback function , which changes status bar caption and start loading workspaces procedure"""
		self.user = self.login_thread.user
		if self.user is None:
			self.statusbar.showMessage("Couldn't auth in LabStep. Please, check internet connection...")
		else:
			#If successful auth --- start reading workspaces
			self.getWorkspaces_thread = getWorkspacesThread(self.user)

			self.getWorkspaces_thread.started.connect(lambda: self.blockUi(True, "Getting workspaces..."))
			self.getWorkspaces_thread.finished.connect(self.gotWorkspaces)

			self.getWorkspaces_thread.start()
			#Parallel getting whole user tags
			self.getUserTags_thread = getExperimentTagsThread(self.user)
			self.getUserTags_thread.finished.connect(self.gotUserTags)
			self.getUserTags_thread.start()

	def blockUi(self, bool_value, msg):
		# Block all UI elements and show message "msg" in status bar...
		self.statusbar.showMessage(msg)
		self.wspComboBox.setDisabled(bool_value)
		self.expTree.setDisabled(bool_value)
		self.tabWidget.setDisabled(bool_value)
		self.tagComboBox.setDisabled(bool_value)

		self.newExpButton.setDisabled(False if not bool_value and self.curWsp.permissions['edit'] else True)

	def LSDateStringToDatetime(self, dt_string):
		"""Covert date-time string to python 'datetime' object"""
		LOCAL_TIMEZONE = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
		dt = dateutil.parser.parse(dt_string).astimezone(LOCAL_TIMEZONE)
		
		return dt

	def showEvent(self, event):
		# Auth to labstep in separated thread
		self.login_thread = loginThread()
		self.login_thread.started.connect(lambda: self.blockUi(True, "Logging in..."))
		self.login_thread.finished.connect(self.loggedIn)
		self.login_thread.start()

def main():
	app = QtWidgets.QApplication(sys.argv)
	window = glx_designApp()
	window.show()
	app.exec_()

if __name__ == "__main__":
	main()
