#!/usr/bin/env python3
# Minimal stand-in for callaudiod on the OnePlus 8 Pro. callaudiod wants a
# speaker and an earpiece port on one PulseAudio sink, which PipeWire does not
# give us, and the call audio does not run through PipeWire anyway (hostless
# voice PCM, see sdx55-callaudio). This serves the same D-Bus interface for
# the dialer and switches the amplifiers directly: the earpiece is the top
# speaker alone at a low gain. Runs in the user session (D-Bus activated).
import subprocess
from gi.repository import Gio, GLib

XML = '''<node><interface name="org.mobian_project.CallAudio">
<method name="SelectMode"><arg direction="in" name="mode" type="u"/><arg direction="out" name="success" type="b"/></method>
<property name="AudioMode" type="u" access="read"/>
<method name="EnableSpeaker"><arg direction="in" name="enable" type="b"/><arg direction="out" name="success" type="b"/></method>
<property name="SpeakerState" type="u" access="read"/>
<method name="MuteMic"><arg direction="in" name="mute" type="b"/><arg direction="out" name="success" type="b"/></method>
<property name="MicState" type="u" access="read"/>
</interface></node>'''
NAME = 'org.mobian_project.CallAudio'
PATH = '/org/mobian_project/CallAudio'
SPEAKER_GAIN, EARPIECE_GAIN, MIC_GAIN = 182, 100, 108
state = {'AudioMode': 0, 'SpeakerState': 0, 'MicState': 0}


def cset(name, val):
    subprocess.run(['amixer', '-q', '-c0', 'cset', "name='%s'" % name, str(val)])


def route():
    earpiece = state['AudioMode'] == 1 and state['SpeakerState'] == 0
    if earpiece:
        cset('Bottom Speaker Switch', 0)
        cset('Top Speaker Volume', EARPIECE_GAIN)
    else:
        cset('Top Speaker Volume', SPEAKER_GAIN)
        cset('Bottom Speaker Switch', 1)
    cset('VA_DEC0 Volume', 0 if state['MicState'] else MIC_GAIN)


def changed(con, key):
    con.emit_signal(None, PATH, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                    GLib.Variant('(sa{sv}as)', (NAME, {key: GLib.Variant('u', state[key])}, [])))


def on_call(con, sender, path, iface, method, params, inv):
    key, val = {'SelectMode': ('AudioMode', lambda v: 1 if v == 1 else 0),
                'EnableSpeaker': ('SpeakerState', int),
                'MuteMic': ('MicState', int)}[method]
    state[key] = val(params.unpack()[0])
    if method == 'SelectMode' and state['AudioMode'] == 0:
        state['SpeakerState'] = state['MicState'] = 0
    route()
    inv.return_value(GLib.Variant('(b)', (True,)))
    for k in state:
        changed(con, k)


def on_get(con, sender, path, iface, prop):
    return GLib.Variant('u', state[prop])


def on_bus(con, name):
    info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
    con.register_object(PATH, info, on_call, on_get, None)


Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.REPLACE, on_bus, None, None)
GLib.MainLoop().run()
