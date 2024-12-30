import wx
import threading
import socket
import aioesphomeapi
from time import sleep
import asyncio
import json
import io
import os
import sys
from datetime import datetime
import logging

import yaml
from pathlib import Path
import  wx.lib.newevent

CallbackEvent, EVT_CALLBACK_EVENT = wx.lib.newevent.NewEvent()
DEBUG = True


class Antenna():
    fallback = False
    def __init__(self, key, name = "", description = "", fallback = False, frequencies = []): 
        self.name = name
        self.key = key
        self.description = description
        self.btn_id = 0
        self.fallback = fallback
        self.frequencies = frequencies

    def __str__(self):
        return self.name
   
    def setBtnId(self, id):
        self.btn_id = id
    

    def getVars(self):
        return { 'name': self.name, 'description': self.description, 'key': self.key, 'fallback': self.fallback, 'frequencies': self.frequencies }

class Frame(wx.Frame):

    _antennas = []
    _running = False
    esp_connect = False
    rb = []
    config = {}
    config_file = None

    async def setup(self):
            try:
                await self.api.connect(login=True)
                sleep(1.5)
                self.esp_connect = True
                entities = await self.api.list_entities_services()
                self._antennas = []
                self.cb_auto.Clear()
                self.cb_auto.Append('Disregard')
                self.cb_auto.Append('None')
                for si in entities[0]:
                    a = Antenna(key = si.key, name = si.name, description = si.name)
                    self.cb_auto.Append(a.name)
                    self._antennas.append(a)
                self.cb_auto.SetSelection(0)
            except:
                wx.MessageBox('Could not contact the ESPHome device. Will quit here.', 'Error', wx.OK | wx.ICON_ERROR)
            finally:
                try:
                    asyncio.run(self.api.disconnect())
                except RuntimeError:
                    pass
            
            # List all entities of the device
            

    def gui_refresh_handler(self, evt):
        ''' We refresh the gui here after an event coming from the ESPHome change '''
        self.rb[evt.rb_id].SetValue(evt.state)
        self.ant_label_lbl.SetLabel(evt.desc)
        self.logger.info(f"Switched to {evt.desc}")

    def __init__(self, title):
        self.logger = logging.getLogger(__name__)
        
        wx.Frame.__init__(self, None, title=title, size=(350,480))

        info_panel  = wx.Panel(self)
        self.cb_auto = wx.Choice(info_panel, -1, choices = ['Disregard', 'None'], style=wx.CB_READONLY)
        
        
        # get the config file from three locations
        home = Path.home()
        self.config_file = Path( os.path.join("/", "etc", "ant_switcher.yml"))
        aside_file  = Path("config.yml")
        home_file   = Path(os.path.join(home,".ant_switcher.yml"))

        # first try aside
        if aside_file.is_file():
            self.config_file = aside_file
        elif home_file.is_file():
            self.config_file = home_file

        enter_setup = False

        self.logger.debug(self.config_file)

        #config_file = Path("/tmp/")
        if self.config_file.is_file():
            with open(self.config_file, 'r') as file:
                self.config = yaml.safe_load(file)
                i = 2
                for ant in self.config['antennas']:
                    a = Antenna(**json.loads(json.dumps(ant)))
                    self._antennas.append(a)     
                    self.cb_auto.Append(a.name)
                    if a.fallback:
                        self.cb_auto.SetSelection(i)
                    i = i + 1

        else:
            enter_setup = True
            self.config['esphome'] = {}
            self.config['esphome']['device'] = 'localhost'
            self.config['esphome']['port']   = 6053
            self.config['esphome']['key']    = '<key>'

            self.config['autoswitch'] = True
            self.config['rig_connect'] = {}
            self.config['rig_connect']['device'] = 'localhost'
            self.config['rig_connect']['port']   = 4532

        if enter_setup:
            td = wx.TextEntryDialog(self, "Please enter the esphome device's hostname or IP address", caption="ESPHome Device Setup",
                    value="")
            td.SetValue(self.config['esphome']['device'])
            resp = td.ShowModal()
            if resp == wx.ID_OK:
                self.config['esphome']['device'] = td.GetValue()
            td = wx.TextEntryDialog(self, "Please enter the esphome device's port", caption="ESPHome Device Setup",
                    value="")

            td.SetValue(str(self.config['esphome']['port']))
            resp = td.ShowModal()
            if resp == wx.ID_OK:
                self.config['esphome']['port'] = td.GetValue()
            td = wx.TextEntryDialog(self, "Please enter the esphome device's key", caption="ESPHome Device Setup",
                    value="")
            td.SetValue(self.config['esphome']['key'])
            resp = td.ShowModal()
            if resp == wx.ID_OK:
                self.config['esphome']['key'] = td.GetValue()
            self.api = aioesphomeapi.APIClient(address=self.config['esphome']['device'], port=self.config['esphome']['port'], password="", noise_psk=self.config['esphome']['key'])

            asyncio.run(self.setup())
            if not self.esp_connect:
                exit(0)

        self.logger.debug(self.config)
        self.cb_auto.Bind(wx.EVT_COMBOBOX, self.onComboBoxSelect)

        panel       = wx.Panel(self)
        rb_panel    = wx.Panel(self)
        
        status_panel  = wx.Panel(self)

        my_sizer    = wx.BoxSizer(wx.VERTICAL) 
        #panel_sizer = wx.BoxSizer(wx.VERTICAL) 
        rb_sizer    = wx.BoxSizer(wx.VERTICAL) 
        gridSizer   = wx.GridSizer(rows=4, cols=2, hgap=5, vgap=5)
        sts_gridSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.freq_label_text = wx.StaticText(info_panel, label = "Frequency:", style = wx.ALIGN_LEFT)
        self.freq_label_lbl = wx.StaticText(info_panel, label = "-.------MHz", style = wx.ALIGN_CENTER)
        self.ant_label_text = wx.StaticText(info_panel, label = "Active Antenna:", style = wx.ALIGN_LEFT)
        self.ant_label_lbl = wx.StaticText(info_panel, label = "", style = wx.ALIGN_CENTER)

        self.status_label = wx.StaticText(status_panel, label = " ", style = wx.ALIGN_CENTER)
        self.status_label2 = wx.StaticText(status_panel, label = "--:--:--", style = wx.ALIGN_CENTER)

        self.auto_cb = wx.CheckBox(info_panel, -1, 'Autoswitch', (10, 10))
        self.auto_cb.SetValue(self.config['autoswitch'])

        fallback_text = wx.StaticText(info_panel, label = "Fallback:", style = wx.ALIGN_LEFT)
        
        

        gridSizer.Add(self.freq_label_text, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        gridSizer.Add(self.freq_label_lbl, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        gridSizer.Add(self.ant_label_text, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        gridSizer.Add(self.ant_label_lbl, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        gridSizer.Add(self.auto_cb, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        gridSizer.Add((0,0), proportion=1)
        gridSizer.Add(fallback_text, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        gridSizer.Add(self.cb_auto, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        
        i = 0
        for ant in self._antennas:
            if i == 0:
                self.rb.append(wx.RadioButton(rb_panel, -1, ant.description, style=wx.RB_GROUP))
            else:
                self.rb.append(wx.RadioButton(rb_panel, -1, ant.description))
            rb_sizer.Add(self.rb[i], 1, wx.ALL | wx.EXPAND, 0)
            i = i + 1
        
        sts_gridSizer.Add(self.status_label, 1, wx.ALL | wx.EXPAND, 0) 
        sts_gridSizer.Add(self.status_label2, 0, wx.ALL | wx.EXPAND, 0) 

        #self.editname = wx.TextCtrl(panel, size=(140, 40), style= wx.TE_MULTILINE | wx.SUNKEN_BORDER)
        #panel_sizer.Add(self.editname, 1, wx.ALL | wx.EXPAND, 5) 
       
        
        info_panel.SetSizer(gridSizer)
        #panel.SetSizer(panel_sizer)
        rb_panel.SetSizer(rb_sizer)
        status_panel.SetSizer(sts_gridSizer)

        my_sizer.Add(info_panel, 0, wx.ALL | wx.EXPAND, 5)
        #my_sizer.Add(panel, 1, wx.ALL | wx.EXPAND, 5) 
        my_sizer.Add(rb_panel, 0, wx.ALL | wx.EXPAND, 5) 
        my_sizer.Add(status_panel, 0, wx.ALL | wx.EXPAND, 5) 
        self.SetSizerAndFit(my_sizer)

        # Make the GUI responsive to the event coming from the ESPHome device 
        self.Bind(EVT_CALLBACK_EVENT, self.gui_refresh_handler)

        self._running = True
        t1 = threading.Thread(target=self.gui)
        t1.daemon = True
        t1.start()
        
        i = 0
        for ant in self._antennas:

            self.Bind(wx.EVT_RADIOBUTTON, self.SetVal, id=self.rb[i].GetId())
            ant.setBtnId(self.rb[i].GetId())
            i = i + 1
        

        t2 = threading.Thread(target=self.worker)
        t2.daemon = True
        t2.start()

        self.Bind(wx.EVT_CLOSE, self.OnCloseFrame)

    def onComboBoxSelect(self, event):
        self.last_freq = 0
            
    def SetVal(self, event):
        try:
            self.api.switch_command(self.getKeyforId(event.GetId()), True)
        except Exception as e:
            print(e)

    def getKeyforId(self, id):
        for ant in self._antennas:
            if ant.btn_id == id:
                return ant.key

    def worker(self):
        freq = 0
        self.last_freq = 0
        HOST = self.config['rig_connect']['device']
        PORT = self.config['rig_connect']['port']
        active_antenna = None
        a = 0
        while self._running:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        wx.CallAfter(self.status_label.SetLabel, f"Connecting to rigctl on {HOST}:{PORT}")
                        sleep(3)
                        s.settimeout(3)
                        s.connect((HOST, PORT))
                        x = s.makefile("rb")

                        wx.CallAfter(self.status_label.SetLabel, f"Connected to rigctl on {HOST}:{PORT}")
                        while self._running:
                            
                            now = datetime.now()
                            wx.CallAfter(self.status_label2.SetLabel, "{}".format(now.strftime("%H:%M:%S")))
                            #print("ping@{}".format(now.strftime("%H:%M:%S")))
                            s.send(b"f\n")
                            data = x.readline().strip()
                            try:
                                freq = int(data.decode('utf-8'))
                            except Exception as e:
                                self.logger.error(e)
                                sleep(1)
                                continue

                            if self.last_freq != freq:
                                wx.CallAfter(self.freq_label_lbl.SetLabel, "{:.6f}MHz".format(freq/1000000.0))

                            fallback_ant = None
                            ant_sel = self.cb_auto.GetSelection()
                            if ant_sel > 1:
                                fallback_ant = self._antennas[ant_sel - 2]


                            if self.auto_cb.GetValue() == True:

                                now = datetime.utcnow()
                                for ant in self._antennas:
                                    for f in ant.frequencies:
                                        if freq >= f['f_begin'] and freq < f['f_end'] and self.last_freq != freq:
                                            if active_antenna != ant:
                                                self.api.switch_command(ant.key, True)
                                            wx.CallAfter(self.status_label.SetLabel, 'For f={:.6f}MHz switching to {} @ {}z\n'.format(freq/1000000.0, ant.name, now.strftime("%H:%M:%S")))
                                            active_antenna = ant
                                            ant_sel = 0
                                            break

                                if self.last_freq != freq and active_antenna != fallback_ant and ant_sel > 0:
                                    if ant_sel == 1:
                                        for ant in self._antennas:
                                            self.api.switch_command(ant.key, False)
                                        active_antenna = None
                                        wx.CallAfter(self.status_label.SetLabel, 'No Antennas\n')
                                        wx.CallAfter(self.ant_label_lbl.SetLabel, 'None')
                                    else:
                                        self.api.switch_command(fallback_ant.key, True)
                                        wx.CallAfter(self.status_label.SetLabel, 'For f={:.6f}MHz switching to {} @ {}z\n'.format(freq/1000000.0, fallback_ant.name, now.strftime("%H:%M:%S")))
                                        active_antenna = fallback_ant
                                
                            elif self.last_freq != freq:
                                wx.CallAfter(self.status_label.SetLabel, 'Autoswitch is off')

                            self.last_freq = freq
                            sleep(1)
            except Exception as e:
                self.logger.error(e)
            sleep(1)

    def change_callback(self, state):
        if type(state) is aioesphomeapi.SwitchState:
            self.logger.debug(state)
            i = 0
            desc = ""
            rb_id = 0
            for ant in self._antennas:

                if state.key == ant.key and len(self.rb) > 0:
                    #self.rb[i].SetValue(state.state)
                    rb_id = i
                    if state.state == True:
                        desc = ant.description
                    break

                i = i + 1
            #create the event
            evt = CallbackEvent(rb_id = rb_id, state = state.state, desc = desc)
            #post the event
            wx.PostEvent(self, evt)

    def gui(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop) 
        asyncio.ensure_future(self.io(subscribe = True))
        self.loop.run_forever()

    async def io(self, subscribe = False):
        self.esp_connect = False
        self.api = aioesphomeapi.APIClient(address=self.config['esphome']['device'], port=self.config['esphome']['port'], password="", noise_psk=self.config['esphome']['key'])
        try:
            await self.api.connect(login=True)
            if subscribe:
                self.api.subscribe_states(self.change_callback)
            self.esp_connect = True
        except:
            wx.MessageBox('Could not contact the ESPHome device. Will quit here.', 'Error', wx.OK | wx.ICON_ERROR)
            self.loop.stop()

    def OnCloseFrame(self, event):
        self._running = False
        
        self.loop.stop()
        
        self.config['antennas'] = []

        for ant in self._antennas:
            self.config['antennas'].append(ant.getVars())    

        with open(self.config_file, 'w') as file:
            yaml.dump(self.config, file)

        wx.CallAfter(self.Destroy)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(message)s', filename='ant_switcher.log', encoding='utf-8', level=logging.DEBUG)
    app = wx.App(redirect=False)
    top = Frame("Antenna Controller v1.0")
    top.Show()
    app.MainLoop()      
