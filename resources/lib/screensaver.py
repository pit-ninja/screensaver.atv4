"""
   Copyright (C) 2015- enen92
   This file is part of screensaver.atv4 - https://github.com/enen92/screensaver.atv4

   SPDX-License-Identifier: GPL-2.0-only
   See LICENSE for more information.
"""

import xbmc
import xbmcgui

from .commonatv import translate, addon, addon_path, notification
from .trans import ScreensaverTrans


def run():
    if not xbmc.getCondVisibility("Player.HasMedia"):
        if not addon.getSettingBool("is_locked"):
            if addon.getSettingBool("show-notifications"):
                notification(translate(32000), translate(32017))

            from resources.lib import atv
            atv.run(False)

        else:
            # Transparent placeholder
            trans = ScreensaverTrans(
                'screensaver-atv4-trans.xml',
                addon_path,
                'default',
                '',
            )
            trans.doModal()
            xbmc.sleep(100)
            del trans
    else:
        # Just call deactivate
        pass
