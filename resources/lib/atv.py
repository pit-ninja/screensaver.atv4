"""
   Copyright (C) 2015- enen92
   This file is part of screensaver.atv4 - https://github.com/enen92/screensaver.atv4

   SPDX-License-Identifier: GPL-2.0-only
   See LICENSE for more information.
"""

import json
import os
import plistlib
import threading
import time

import xbmc
import xbmcgui
import xbmcvfs

from .commonatv import translate, addon, addon_path
from .offline import offline
from .playlist import AtvPlaylist
from .trans import ScreensaverTrans

def format_location(s):
    if len(s) > 55 and '\n' not in s:
        middle = len(s) // 2
        spaces = [i for i, c in enumerate(s) if c == ' ']
        if spaces:
            closest_space = min(spaces, key=lambda x: abs(x - middle))
            return s[:closest_space] + '\n' + s[closest_space+1:]
    return s

monitor = xbmc.Monitor()


class Screensaver(xbmcgui.WindowXML):

    def __init__(self, *args, **kwargs):
        self.DPMStime = json.loads(xbmc.executeJSONRPC(
            '{"jsonrpc":"2.0","method":"Settings.GetSettingValue","params":{"setting":"powermanagement.displaysoff"},"id":2}'))[
                            'result']['value'] * 60
        self.isDPMSactive = bool(self.DPMStime > 0)
        self.active = True
        self.atv4player = None
        self.video_playlist = AtvPlaylist().compute_playlist_array()
        xbmc.log(msg=f"kodi dpms time: {self.DPMStime}", level=xbmc.LOGDEBUG)
        xbmc.log(msg=f"kodi dpms active: {self.isDPMSactive}", level=xbmc.LOGDEBUG)

        # CoreELEC DV Luminance Hijack placeholders
        self.dv_setting_id = "coreelec.amlogic.dolbyvision.osd.brightness"
        self.original_dv_luminance = None

    def onInit(self):
        self.setProperty("screensaver-atv4-loading", "true")
        self.setProperty("show-info", addon.getSetting("show-info"))

        # Apply CoreELEC DV Luminance Hijack
        if addon.getSettingBool("enable-hdr") and addon.getSettingBool("show-info") and not addon.getSettingBool("ce-dv-follow"):
            target_luminance = addon.getSettingInt("ce-dv-brightness")
            try:
                resp = xbmc.executeJSONRPC(f'{{"jsonrpc":"2.0","method":"Settings.GetSettingValue","params":{{"setting":"{self.dv_setting_id}"}},"id":1}}')
                self.original_dv_luminance = json.loads(resp)['result']['value']
                
                if self.original_dv_luminance != target_luminance:
                    xbmc.executeJSONRPC(f'{{"jsonrpc":"2.0","method":"Settings.SetSettingValue","params":{{"setting":"{self.dv_setting_id}", "value": {target_luminance}}},"id":1}}')
                else:
                    self.original_dv_luminance = None 
            except Exception:
                pass

        if self.video_playlist:
            self.setProperty("screensaver-atv4-loading", "false")
            self.atv4player = xbmc.Player()

            threading.Thread(target=self.start_playback).start()

            self.max_allowed_time = None
            if self.isDPMSactive and addon.getSettingInt("check-dpms") == 1:
                self.max_allowed_time = self.DPMStime
            elif addon.getSettingInt("check-dpms") == 2:
                self.max_allowed_time = addon.getSettingInt("manual-dpms") * 60

            if self.max_allowed_time:
                delta = 0
                while self.active:
                    if not xbmc.getCondVisibility("System.ScreenSaverActive"):
                        self.onAction(None)
                        break
                    if delta >= self.max_allowed_time:
                        self.activateDPMS()
                        break
                    monitor.waitForAbort(0.05)
                    delta += 0.05
        else:
            self.novideos()

    def activateDPMS(self):
        self.active = False
        enable_window_placeholder = False
        if addon.getSettingInt("dpms-action") == 0:
            if self.atv4player:
                self.atv4player.pause()
        else:
            self.clearAll()
            enable_window_placeholder = True

        if addon.getSettingBool("toggle-displayoff") or addon.getSetting("toggle-cecoff") == "true" or addon.getSettingBool("toggle-systemoff"):
            monitor.waitForAbort(1)

        if addon.getSettingBool("toggle-displayoff"):
            try:
                xbmc.executebuiltin('ToggleDPMS')
            except Exception:
                pass

        if addon.getSetting("toggle-cecoff") == "true":
            try:
                xbmc.executebuiltin('CECStandby')
            except Exception:
                pass

        if addon.getSettingBool("toggle-systemoff"):
            try:
                xbmc.executebuiltin('ShutDown')
            except Exception:
                pass

        if enable_window_placeholder:
            self.toTransparent()

    def novideos(self):
        self.setProperty("screensaver-atv4-loading", "false")
        pass

    @classmethod
    def toTransparent(self):
        trans = ScreensaverTrans('screensaver-atv4-trans.xml', addon_path, 'default', '')
        trans.doModal()
        xbmc.sleep(100)
        del trans

    def clearAll(self, close=True):
        self.active = False
        
        # Restore CoreELEC DV Luminance if hijacked
        if getattr(self, 'original_dv_luminance', None) is not None:
            try:
                xbmc.executeJSONRPC(f'{{"jsonrpc":"2.0","method":"Settings.SetSettingValue","params":{{"setting":"{self.dv_setting_id}", "value": {self.original_dv_luminance}}},"id":1}}')
            except Exception:
                pass
                
        if self.atv4player:
            self.atv4player.stop()
            
        self.close()

    def onAction(self, action):
        addon.setSettingBool("is_locked", False)
        self.clearAll()

    def start_playback(self):
        # Determine language for localized strings
        lang_code = xbmc.getLanguage(xbmc.ISO_639_1)
        if not lang_code:
            lang_code = "en"
            
        strings_path = os.path.join(addon_path, "resources", "TVIdleScreenStrings.bundle", f"{lang_code}.lproj", "Localizable.nocache.strings")
        if not xbmcvfs.exists(strings_path):
            # Fallback to English if the localized file doesn't exist
            strings_path = os.path.join(addon_path, "resources", "TVIdleScreenStrings.bundle", "en.lproj", "Localizable.nocache.strings")
            
        localized_strings = {}
        if xbmcvfs.exists(strings_path):
            try:
                with open(xbmcvfs.translatePath(strings_path), "rb") as f:
                    localized_strings = plistlib.load(f)
            except Exception as e:
                xbmc.log(f"Failed to load localized strings: {e}", level=xbmc.LOGWARNING)

        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()
        
        url_to_video = {}
        for video in self.video_playlist:
            url = video["url"]
            location = video["location"]
            
            # Retrieve localized string if possible
            poi = video.get("pointsOfInterest", {})
            poi_0 = poi.get("0")
            
            if poi_0 and poi_0 in localized_strings:
                location = localized_strings[poi_0]
                
            list_item = xbmcgui.ListItem(location)
            playlist.add(url=url, listitem=list_item)
            url_to_video[url] = video

        self.atv4player.play(playlist, windowed=True)
        
        current_playing_url = None
        is_transitioning = True
        
        current_location_text = None
        poi_transitioning = False
        poi_transition_start_time = 0
        self.setProperty("poi-fade-out", "false")
        try:
            fade_delay = float(addon.getSetting("fade-delay"))
        except Exception:
            fade_delay = 1.0
        
        while self.active and not monitor.abortRequested():
            if not xbmc.getCondVisibility("System.ScreenSaverActive"):
                self.onAction(None)
                break
                
            monitor.waitForAbort(0.05)
            
            if self.active and self.atv4player.isPlaying():
                try:
                    total_time = self.atv4player.getTotalTime()
                    current_time = self.atv4player.getTime()
                    playing_url = self.atv4player.getPlayingFile()
                    
                    video_info = url_to_video.get(playing_url, {})
                    poi_dict = video_info.get("pointsOfInterest", {})
                    
                    current_poi_key = None
                    for poi_time_str in sorted(poi_dict.keys(), key=int):
                        if int(poi_time_str) <= current_time:
                            current_poi_key = poi_time_str
                        else:
                            break
                            
                    new_location = video_info.get("location", "")
                    if current_poi_key and poi_dict[current_poi_key] in localized_strings:
                        new_location = localized_strings[poi_dict[current_poi_key]]
                    elif "0" in poi_dict and poi_dict["0"] in localized_strings:
                        new_location = localized_strings[poi_dict["0"]]

                    new_location = format_location(new_location)

                    if playing_url != current_playing_url:
                        current_playing_url = playing_url
                        is_transitioning = True
                        poi_transitioning = False
                        self.setProperty("poi-fade-out", "false")
                        
                    if new_location != current_location_text:
                        if current_location_text is not None and not is_transitioning and not poi_transitioning:
                            poi_transitioning = True
                            poi_transition_start_time = time.time()
                            self.setProperty("poi-fade-out", "true")
                            
                        if poi_transitioning and time.time() >= poi_transition_start_time + 2.0:
                            current_location_text = new_location
                            parts = new_location.split('\n', 1)
                            if len(parts) == 2:
                                self.setProperty('AerialLocationLine1', parts[0])
                                self.setProperty('AerialLocationLine2', parts[1])
                            else:
                                self.setProperty('AerialLocationLine1', '')
                                self.setProperty('AerialLocationLine2', new_location)
                                
                            self.setProperty("poi-fade-out", "false")
                            poi_transitioning = False
                            
                        elif not poi_transitioning:
                            current_location_text = new_location
                            parts = new_location.split('\n', 1)
                            if len(parts) == 2:
                                self.setProperty('AerialLocationLine1', parts[0])
                                self.setProperty('AerialLocationLine2', parts[1])
                            else:
                                self.setProperty('AerialLocationLine1', '')
                                self.setProperty('AerialLocationLine2', new_location)
                    
                    if total_time > 0 and (total_time - current_time) <= 2.5:
                        is_transitioning = True
                        
                    elif is_transitioning and fade_delay <= current_time < (fade_delay + 10.0):
                        is_transitioning = False

                    if is_transitioning:
                        self.setProperty("fade-black", "true")
                    else:
                        self.setProperty("fade-black", "false")
                        
                except Exception:
                    self.setProperty("fade-black", "true")
                    pass
                    
            elif self.active and not self.atv4player.isPlaying():
                self.setProperty("fade-black", "true")
                
                # Debounce: Wait up to 3 seconds to let Kodi natively load the next file
                recovery_ticks = 0
                while self.active and not self.atv4player.isPlaying() and recovery_ticks < 60:
                    if not xbmc.getCondVisibility("System.ScreenSaverActive"):
                        self.onAction(None)
                        break
                    monitor.waitForAbort(0.05)
                    recovery_ticks += 1
                
                # If it is STILL stopped after 3 seconds, the playlist naturally ended or network dropped
                if self.active and not self.atv4player.isPlaying():
                    self.atv4player.play(playlist, windowed=True)

def run(params=False):
    if not params:
        addon.setSettingBool("is_locked", True)
        screensaver = Screensaver('screensaver-atv4.xml', addon_path, 'default', '')
        screensaver.setProperty("fade-black", "true")
        screensaver.doModal()
        xbmc.sleep(100)
        del screensaver
    else:
        offline()
