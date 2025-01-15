import wx



class SettingsFrame(wx.Frame):

    def __init__(self, title):
    
        wx.Frame.__init__(self, None, title=title, size=(320, 480), style=wx.CAPTION | wx.SYSTEM_MENU | wx.CLOSE_BOX)

        panel = wx.Panel(self)

        vbox = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(vbox)
        buttonsBox = wx.StdDialogButtonSizer()
        vbox.Add(buttonsBox, 1,
                  wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT)
        cancelButn = wx.Button(panel, wx.ID_CANCEL)
        buttonsBox.AddButton(cancelButn)
        okButn = wx.Button(panel, wx.ID_OK)
        buttonsBox.AddButton(okButn)
        okButn.SetDefault()
        buttonsBox.Realize()

        #cancelButn.Bind(wx.EVT_BUTTON, self.OnCancel)
        #okButn.Bind(wx.EVT_BUTTON, self.OnOK)

# for testing only
if __name__ == '__main__':
    app = wx.App(redirect=False)
    sf = SettingsFrame("Settings")
    sf.Show()
    app.MainLoop() 
