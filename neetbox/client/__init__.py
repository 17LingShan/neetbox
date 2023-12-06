# -*- coding: utf-8 -*-
#
# Author: GavinGong aka VisualDust
# URL:    https://gong.host
# Date:   20231206

from ._client_action_agent import _NeetActionManager as NeetActionManager
from ._image import add_image
from ._plots import add_scatter
from ._signal_and_slot import listen, watch

action = NeetActionManager.register

__all__ = ["add_image", "add_scatter", "action", "NeetActionManager", "watch", "listen"]
