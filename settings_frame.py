import wx



class SettingsFrame(wx.Frame):

    def __init__(self, title):
    
        wx.Frame.__init__(self, None, title=title, size=(320, 480), style=wx.CAPTION | wx.SYSTEM_MENU | wx.CLOSE_BOX)



# for testing only
if __name__ == '__main__':
    app = wx.App(redirect=False)
    sf = SettingsFrame("Settings")
    sf.Show()
    app.MainLoop() 
