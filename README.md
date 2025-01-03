# Antenna-Switcher

It is a program that controls a ESPHome device to switch antennas remotely. The switching can be done based on the frequency that is set on the rig.

```
- description: Dipole 10/20m
  fallback: false
  frequencies:
  - f_begin: 14000000
    f_end: 14350000
  - f_begin: 28000000
    f_end: 29700000
  key: 655527339
  name: Antenna 4
```

It has a GUI based on wxWidgets (wxPython).

![image](https://github.com/user-attachments/assets/02ae5e82-feea-4710-b26c-0294aea4eb85)

As it is based on python, it can be run on all major platforms. You need a ESPHome device (e.g. ESP32 based board like a NodeMCU).
