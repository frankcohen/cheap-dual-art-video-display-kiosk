#!/usr/bin/env python3
"""Cheap Dual Art Video Display Kiosk player (Raspberry Pi 5)."""
from pathlib import Path
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gst, GLib, Gdk

Gst.init(None)
BASE = Path.home() / 'Videos' / 'dual-art-kiosk'
LEFT = BASE / 'TestLeft_H265.mp4'
RIGHT = BASE / 'TestRight_H265.mp4'
AUDIO = BASE / 'sounds.wav'
WIDTH, HEIGHT = 1920, 1080
CROP_BOTTOM = 5
AUDIO_DEVICES = ('plughw:0,0', 'plughw:1,0')

for filename in (LEFT, RIGHT, AUDIO):
    if not filename.is_file():
        raise SystemExit(f'Missing file: {filename}')

pipeline = Gst.Pipeline.new('dual-art-kiosk')
windows = []

def make_element(factory, name):
    element = Gst.ElementFactory.make(factory, name)
    if element is None:
        raise RuntimeError(f'Cannot create GStreamer element: {factory}')
    return element

def link_elements(*elements):
    for upstream, downstream in zip(elements, elements[1:]):
        if not upstream.link(downstream):
            raise RuntimeError(f'Cannot link {upstream.get_name()} to {downstream.get_name()}')

def create_video_branch(index, filename):
    source = make_element('filesrc', f'source{index}')
    source.set_property('location', str(filename))
    demux = make_element('qtdemux', f'demux{index}')
    parser = make_element('h265parse', f'parser{index}')
    decoder = make_element('v4l2slh265dec', f'decoder{index}')
    queue = make_element('queue', f'video_queue{index}')
    upload = make_element('glupload', f'upload{index}')
    glconvert = make_element('glcolorconvert', f'glconvert{index}')
    transform = make_element('gltransformation', f'gl_transform{index}')
    transform.set_property('scale-y', HEIGHT / (HEIGHT - CROP_BOTTOM))
    transform.set_property('translation-y', CROP_BOTTOM / HEIGHT)
    sink = make_element('gtkglsink', f'video_sink{index}')
    sink.set_property('sync', True)

    window = Gtk.Window(title=f'Art Video {index + 1}')
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_default_size(WIDTH, HEIGHT)
    window.add(sink.get_property('widget'))
    window.connect('destroy', Gtk.main_quit)
    windows.append(window)

    for element in (source, demux, parser, decoder, queue, upload, glconvert, transform, sink):
        pipeline.add(element)
    link_elements(source, demux)
    link_elements(parser, decoder, queue, upload, glconvert, transform, sink)

    def on_video_pad(element, pad):
        caps = pad.get_current_caps() or pad.query_caps(None)
        if not caps or caps.get_size() == 0:
            return
        if caps.get_structure(0).get_name().startswith('video/'):
            target = parser.get_static_pad('sink')
            if not target.is_linked():
                result = pad.link(target)
                if result != Gst.PadLinkReturn.OK:
                    print(f'Video {index + 1} link error: {result}', flush=True)

    demux.connect('pad-added', on_video_pad)
    print(f'Video {index + 1}: {filename}', flush=True)

create_video_branch(0, LEFT)
create_video_branch(1, RIGHT)

def create_audio_branch(filename):
    source = make_element('filesrc', 'audio_source')
    source.set_property('location', str(filename))
    decoder = make_element('decodebin', 'audio_decoder')
    convert = make_element('audioconvert', 'audio_convert')
    resample = make_element('audioresample', 'audio_resample')
    tee = make_element('tee', 'audio_tee')
    for element in (source, decoder, convert, resample, tee):
        pipeline.add(element)
    link_elements(source, decoder)
    link_elements(convert, resample, tee)

    for index, device in enumerate(AUDIO_DEVICES):
        queue = make_element('queue', f'audio_queue{index}')
        sink = make_element('alsasink', f'audio_sink{index}')
        sink.set_property('device', device)
        sink.set_property('sync', True)
        pipeline.add(queue)
        pipeline.add(sink)
        link_elements(queue, sink)
        if not tee.link(queue):
            raise RuntimeError(f'Cannot connect audio to HDMI device {device}')
        print(f'Audio output {index + 1}: {device}', flush=True)

    def on_decoder_pad(element, pad):
        caps = pad.get_current_caps() or pad.query_caps(None)
        if not caps or caps.get_size() == 0:
            return
        if caps.get_structure(0).get_name().startswith('audio/x-raw'):
            target = convert.get_static_pad('sink')
            if not target.is_linked():
                result = pad.link(target)
                if result != Gst.PadLinkReturn.OK:
                    print(f'Audio decoder link error: {result}', flush=True)

    decoder.connect('pad-added', on_decoder_pad)
    print(f'Soundtrack: {filename}', flush=True)
    print('Stereo soundtrack routed to both HDMI monitors.', flush=True)

create_audio_branch(AUDIO)

for window in windows:
    window.show_all()
    display = Gdk.Display.get_default()
    cursor = Gdk.Cursor.new_for_display(display, Gdk.CursorType.BLANK_CURSOR)
    window.get_window().set_cursor(cursor)
    # labwc rules must place each window on its intended output.
    GLib.idle_add(window.fullscreen)

bus = pipeline.get_bus()
bus.add_signal_watch()

def on_message(bus, message):
    if message.type == Gst.MessageType.ERROR:
        error, debug = message.parse_error()
        print(f'GStreamer error: {error}', flush=True)
        if debug:
            print(debug, flush=True)
        Gtk.main_quit()
    elif message.type == Gst.MessageType.EOS:
        print('Loop complete. Restarting both videos and soundtrack...', flush=True)
        success = pipeline.seek_simple(Gst.Format.TIME,
                                       Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, 0)
        if not success:
            print('Loop seek failed.', flush=True)
            Gtk.main_quit()

bus.connect('message', on_message)
print('Starting dual-art kiosk dual-monitor installation...', flush=True)
print(f'Display resolution: {WIDTH} x {HEIGHT}', flush=True)
print(f'Bottom-edge correction: {CROP_BOTTOM} pixels', flush=True)
print('Video: hardware H.265 decoding', flush=True)
print('Audio: external stereo WAV to both HDMI monitors', flush=True)
print('Mouse pointer: hidden', flush=True)
print('Playback: continuous synchronized looping', flush=True)
result = pipeline.set_state(Gst.State.PLAYING)
if result == Gst.StateChangeReturn.FAILURE:
    raise RuntimeError('Failed to start GStreamer pipeline')
try:
    Gtk.main()
except KeyboardInterrupt:
    print('\nStopping dual-art kiosk player...', flush=True)
finally:
    pipeline.set_state(Gst.State.NULL)
    print('dual-art kiosk player stopped.', flush=True)
