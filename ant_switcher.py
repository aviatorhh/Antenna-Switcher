import wx
import threading
import socket
import aioesphomeapi
from aioesphomeapi.reconnect_logic import (
    MAXIMUM_BACKOFF_TRIES,
    ReconnectLogic,
    ReconnectLogicState,
)
from time import sleep
import asyncio
import json
import io
import os
import sys
from datetime import datetime
import tzlocal
import logging
from logging.handlers import RotatingFileHandler
from apscheduler.schedulers.background import BackgroundScheduler
import yaml
from pathlib import Path
import  wx.lib.newevent

from settings_frame import SettingsFrame

CallbackEvent, EVT_CALLBACK_EVENT = wx.lib.newevent.NewEvent()
StalledEvent, EVT_STALLED_EVENT = wx.lib.newevent.NewEvent()

scheduler = BackgroundScheduler()

NONE_BTN = -1

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
   
    def set_btn_id(self, id):
        self.btn_id = id
    

    def get_vars(self):
        return { 'name': self.name, 'description': self.description, 'key': self.key, 'fallback': self.fallback, 'frequencies': self.frequencies }

class MainFrame(wx.Frame):

    _antennas = []
    _running = False
    _esp_connect = False
    rb = []
    config = {}
    config_file = None
    _ant_response_count = 0

    async def setup(self):
            try:
                await self.api.connect(login=True)
                sleep(1.5)
                self._esp_connect = True
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
        self._ant_response_count = self._ant_response_count + 1
        ''' first set none if false 
        This is done because the radio button group cannot have no state
        '''
        if evt.state == False and self._ant_response_count >= len(self.rb):
            self.rb[evt.rb_id].SetValue(False)
            self.rb[len(self.rb) - 1].SetValue(True)
            return

        self.rb[evt.rb_id].SetValue(evt.state)
        self.rb[evt.rb_id].Enable()

        self.logger.info(f"Got state {evt.state} of {evt.desc} for {evt.rb_id}")
        if evt.state == True:
            self.ant_label_lbl.SetLabel(evt.desc)
            self.logger.info(f"Switched to {evt.desc}")


    def menu_handler(self, event): 
        id = event.GetId() 

        if id == self.quit.GetId():
            self.on_close_frame(None)

        if id == self.settings.GetId():
            sf = SettingsFrame("Settings")
            sf.Show()

    def __init__(self, title):
        self.locale = wx.Locale(wx.LANGUAGE_ENGLISH)
        self.logger = logging.getLogger(__name__)
    
        wx.Frame.__init__(self, None, title=title, size=(480, 348), style=wx.CAPTION | wx.SYSTEM_MENU | wx.CLOSE_BOX)

        self.menu_bar = wx.MenuBar()
        fileMenu = wx.Menu()
        utilsMenu = wx.Menu()
        self.quit = wx.MenuItem(fileMenu, wx.ID_EXIT, "Exit", "Close")
        self.utils = wx.MenuItem(utilsMenu, wx.ID_ANY, "Sync Rig Clock", kind = wx.ITEM_CHECK)
        self.settings = wx.MenuItem(utilsMenu, wx.ID_ANY, "Settings")

        fileMenu.Append(self.quit)
        utilsMenu.Append(self.utils)
        utilsMenu.Append(self.settings)
        self.menu_bar.Append(fileMenu, 'App')
        self.menu_bar.Append(utilsMenu, 'Utils')

        
        self.SetMenuBar(self.menu_bar) 

        self.Bind(wx.EVT_MENU, self.menu_handler)

        panel       = wx.Panel(self)
        info_panel    = wx.Panel(panel)
        self.cb_auto = wx.Choice(info_panel, -1, choices = ['Disregard', 'None'], style = wx.CB_READONLY)
        
        
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

        self.logger.addHandler(RotatingFileHandler(self.config['logging']['logfile'], maxBytes=1024 * 1000, backupCount=1))

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
            if not self._esp_connect:
                exit(0)

        self.logger.debug(self.config)

        self.utils.Check(self.config['sync_clock'])

        self.cb_auto.Bind(wx.EVT_COMBOBOX, self.on_combobox_select)
        
        rb_panel    = wx.Panel(panel)
        
        main_sizer    = wx.BoxSizer(wx.VERTICAL) 
        rb_sizer    = wx.BoxSizer(wx.VERTICAL) 
        info_sizer   = wx.GridSizer(rows=4, cols=2, hgap=0, vgap=0)
        
        freq_label_text = wx.StaticText(info_panel, label = "Frequency:", style = wx.ALIGN_LEFT)
        self.freq_label_lbl = wx.StaticText(info_panel, label = "-.------MHz", style = wx.ALIGN_CENTER)
        f = self.freq_label_lbl.GetFont()
        f.SetFaceName("DejaVu Sans Mono")
        self.freq_label_lbl.SetFont(f)

        ant_label_text = wx.StaticText(info_panel, label = "Active Antenna:", style = wx.ALIGN_LEFT)
        self.ant_label_lbl = wx.StaticText(info_panel, label = "", style = wx.ALIGN_CENTER)
        fallback_text = wx.StaticText(info_panel, label = "Fallback:", style = wx.ALIGN_LEFT)

        self.status_bar = self.CreateStatusBar(2)
        self.status_bar.SetStatusWidths([-1, 80])
        self.status_bar.SetStatusText("Trying to connect to the antenna switcher ...")
        self.status_bar.SetStatusText("", 1)

        self.auto_cb = wx.CheckBox(info_panel, -1, 'Autoswitch', (10, 10))
        self.auto_cb.SetValue(self.config['autoswitch'])

        info_sizer.Add(freq_label_text, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(self.freq_label_lbl, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(ant_label_text, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(self.ant_label_lbl, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(self.auto_cb, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add((0,0))
        info_sizer.Add(fallback_text, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(self.cb_auto, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        
        i = 0
        for ant in self._antennas:
            if i == 0:
                self.rb.append(wx.RadioButton(rb_panel, -1, ant.description, style=wx.RB_GROUP))
            else:
                self.rb.append(wx.RadioButton(rb_panel, -1, ant.description))
            rb_sizer.Add(self.rb[i], 1, wx.ALL | wx.EXPAND, 0)
            self.rb[i].Disable()
            i = i + 1

        self.rb.append(wx.RadioButton(rb_panel, -1, "None"))
        rb_sizer.Add(self.rb[i], 1, wx.ALL | wx.EXPAND, 0)
        # Initially set the None state as we do not know by now
        self.rb[len(self.rb)-1].SetValue(True) 

        info_panel.SetSizer(info_sizer)
        rb_panel.SetSizer(rb_sizer)
        
        main_sizer.Add(info_panel, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(rb_panel, 0, wx.ALL | wx.EXPAND, 5) 
        panel.SetSizerAndFit(main_sizer)
        
        i = 0
        for ant in self._antennas:

            self.Bind(wx.EVT_RADIOBUTTON, self.set_val, id=self.rb[i].GetId())
            ant.set_btn_id(self.rb[i].GetId())
            i = i + 1
        self.Bind(wx.EVT_RADIOBUTTON, self.set_val, id=self.rb[i].GetId())

        # Make the GUI responsive to the event coming from the ESPHome device 
        self.Bind(EVT_CALLBACK_EVENT, self.gui_refresh_handler)
        self._running = True
        self.api_worker_thread = threading.Thread(target=self.api_worker)
        self.api_worker_thread.daemon = True
        self.api_worker_thread.start()

        # Make the GUI responsive to the event coming from the ESPHome device 
        self.Bind(EVT_STALLED_EVENT, self.stalled_handler)
        self.worker_thread = threading.Thread(target=self.worker)
        self.worker_thread.daemon = True
        self.worker_thread.start()

        
        self.Bind(wx.EVT_CLOSE, self.on_close_frame)

    def on_combobox_select(self, event):
        self.last_freq = 0
            
    def set_val(self, event):
        key = self.get_key_for_id(event.GetId())

        if key == NONE_BTN:
            for rb in self.rb:
                try:
                    self.api.switch_command(self.get_key_for_id(rb.GetId()), False)
                except Exception as e:
                    self.logger.error(e)
        else:

            try:
                self.api.switch_command(key, True)
            except Exception as e:
                self.logger.error(e)
                self._running = False
                self.loop.stop()
                evt = StalledEvent()
                #post the event
                wx.PostEvent(self, evt)

    def get_key_for_id(self, id):
        for ant in self._antennas:
            if ant.btn_id == id:
                return ant.key
        return NONE_BTN


    def is_number_repl_isdigit(self, s):
        """ Returns True if string is a number. """
        return s.replace('.','',1).isdigit()

    def worker(self):
        freq = 0
        mode = ""
        self.last_freq = 0
        HOST = self.config['rig_connect']['device']
        PORT = self.config['rig_connect']['port']
        active_antenna = None
        a = 0

        while self._running:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        wx.CallAfter(self.status_bar.SetStatusText, f"Connecting to rigctl on {HOST}:{PORT}")
                        sleep(3)
                        s.settimeout(3)
                        s.connect((HOST, PORT))
                        x = s.makefile("rb")

                        wx.CallAfter(self.status_bar.SetStatusText, f"Connected to rigctl on {HOST}:{PORT}")
                        while self._running:
                            
                            now = datetime.now()
                            wx.CallAfter(self.status_bar.SetStatusText, "{}".format(now.strftime("%H:%M:%S")), 1)
                            s.send(b"fm\n")
                            data = x.readline().strip()
                            try:
                                freq = int(data.decode('utf-8'))
                                data = x.readline().strip()
                                if self.is_number_repl_isdigit(data.decode('utf-8')):
                                    raise Exception(f"{data} should not be a number")
                                mode = str(data.decode('utf-8'))
                                data = x.readline().strip()
                            except Exception as e:
                                self.logger.error(f"The rig communication has failed\n{e}")
                                s.shutdown(socket.SHUT_RDWR)
                                s.close()
                                sleep(1)
                                raise Exception("Read error")

                            if self.last_freq != freq:
                                wx.CallAfter(self.freq_label_lbl.SetLabel, "{:.6f}MHz ({})".format(freq/1000000.0, mode))

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
                                                try:
                                                    self.api.switch_command(ant.key, True)
                                                except Exception as e:
                                                    self.logger.error(f"{e}\nWe need to restart the worker and reconnect.")
                                                    self._running = False
                                            wx.CallAfter(self.status_bar.SetStatusText, 'For f={:.6f}MHz switching to {} @ {}z\n'.format(freq/1000000.0, ant.name, now.strftime("%H:%M:%S")))
                                            active_antenna = ant
                                            ant_sel = 0
                                            break

                                if self.last_freq != freq and active_antenna != fallback_ant and ant_sel > 0:
                                    if ant_sel == 1:
                                        for ant in self._antennas:
                                            self.api.switch_command(ant.key, False)
                                        active_antenna = None
                                        wx.CallAfter(self.status_bar.SetStatusText, 'No Antennas\n')
                                        wx.CallAfter(self.ant_label_lbl.SetLabel, 'None')
                                    else:
                                        self.api.switch_command(fallback_ant.key, True)
                                        wx.CallAfter(self.status_bar.SetStatusText, 'For f={:.6f}MHz switching to {} @ {}z\n'.format(freq/1000000.0, fallback_ant.name, now.strftime("%H:%M:%S")))
                                        active_antenna = fallback_ant
                                
                            elif self.last_freq != freq:
                                wx.CallAfter(self.status_bar.SetStatusText, 'Autoswitch is off')

                            self.last_freq = freq
                            sleep(1)
            except Exception as e:
                self.logger.error(f"Something went wrong talking to the rig!\n{e}")
            sleep(1)
        self.loop.stop()
        evt = StalledEvent()
        #post the event
        wx.PostEvent(self, evt)
        self.logger.debug("Stopped {self.worker.__name__}")

    def change_callback(self, state):
        if type(state) is aioesphomeapi.SwitchState:
            self.logger.debug(state)
            i = 0
            desc = ""
            rb_id = 0
            for ant in self._antennas:

                if state.key == ant.key:
                    rb_id = i
                    if state.state == True:
                        desc = ant.description
                    break

                i = i + 1
            #if state.state == True:
            #create the event
            evt = CallbackEvent(rb_id = rb_id, state = state.state, desc = desc)
            #post the event
            wx.PostEvent(self, evt)

    def api_worker(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop) 
        asyncio.ensure_future(self.api_connect(subscribe = True))
        self.loop.run_forever()
        self.logger.debug("Stopped {self.api_worker.__name__}")

    async def api_connect(self, subscribe = False):
        self._esp_connect = False
        self.api = aioesphomeapi.APIClient(address=self.config['esphome']['device'], port=self.config['esphome']['port'], password="", noise_psk=self.config['esphome']['key'])
        async def on_disconnect(expected_disconnect: bool) -> None:
            self.logger.debug("disconnected")

        async def on_connect() -> None:
            self.logger.debug("connected")

        ReconnectLogic(
            client=self.api,
            on_disconnect=on_disconnect,
            on_connect=on_connect
        )
        try:
            await self.api.connect(login=True)
            if subscribe:
                self.api.subscribe_states(self.change_callback)
            self.logger.info(await self.api.device_info())
            self._esp_connect = True
        except:
            wx.MessageBox('Could not contact the ESPHome device. Will quit here.', 'Error', wx.OK | wx.ICON_ERROR)
            self.loop.stop()

    def on_close_frame(self, event):
        self._running = False
        sleep(1.5)
        #self.loop.stop()
        
        self.config['antennas'] = []

        for ant in self._antennas:
            self.config['antennas'].append(ant.get_vars())    

        self.config['sync_clock'] = self.utils.IsChecked()

        with open(self.config_file, 'w') as file:
            yaml.dump(self.config, file)

        wx.CallAfter(self.Destroy)

    def stalled_handler(self, event):
        self.logger.debug(event)
        self._running = True
        self.api_worker_thread = threading.Thread(target=self.api_worker)
        self.api_worker_thread.daemon = True
        self.api_worker_thread.start()
        self.worker_thread = threading.Thread(target=self.worker)
        self.worker_thread.daemon = True
        self.worker_thread.start()


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)
    app = wx.App(redirect=False)
    top = MainFrame("Antenna Controller v1.1")

    @scheduler.scheduled_job('cron', hour='0-23', minute='0,10,20,30,40,50')
    def sync_time():
        if top.utils.IsChecked():
            HOST = top.config['rig_connect']['device']
            PORT = top.config['rig_connect']['port']
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                ts = datetime.now(tzlocal.get_localzone()).strftime("%Y-%m-%dT%H:%M:%S%z")
                s.send(f"\\set_clock {ts}\r\n".encode('utf-8'))
                top.logger.info(f"Synced rig clock to {ts}")
                wx.CallAfter(top.status_bar.PopStatusText, f"Synced rig clock to {ts}")
    top.Show()
    scheduler.start()
    app.MainLoop()      

