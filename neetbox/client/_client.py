# -*- coding: utf-8 -*-
#
# Author: GavinGong aka VisualDust
# Github: github.com/visualDust
# Date:   20231022

import json
import logging
import subprocess
import time
from collections import defaultdict
from threading import Thread
from typing import Callable

import httpx
import websocket

from neetbox._protocol import *
from neetbox.config import get_module_level_config, get_project_id, get_run_id
from neetbox.logging.formatting import LogStyle
from neetbox.logging.logger import Logger
from neetbox.utils import DaemonableProcess
from neetbox.utils.massive import is_loopback
from neetbox.utils.mvc import Singleton

logging.getLogger("httpx").setLevel(logging.ERROR)
logger = Logger(whom=None, style=LogStyle(skip_writers=["ws"]))


def addr_of_api(api, http_root=None):
    if not http_root:
        config = get_module_level_config()
        daemon_server_address = f"{config['host']}:{config['port']}"
        http_root = f"http://{daemon_server_address}"
    if not api.startswith("/"):
        api = f"/{api}"
    return f"{http_root}{api}"


class NeetboxClient(metaclass=Singleton):  # singleton
    # statics
    online_mode: bool = None
    httpxClient: httpx.Client = httpx.Client(  # httpx client
        proxies={
            "http://": None,
            "https://": None,
        }
    )  # type: ignore
    wsApp: websocket.WebSocketApp = None  # websocket client app
    __initialized: bool = False
    is_ws_connected: bool = False
    ws_message_query = []  # websocket message query
    ws_subscribers = defaultdict(list)  # default to no subscribers

    def post(self, api: str, root: str = None, *args, **kwargs):
        url = addr_of_api(api, http_root=root)
        return self.httpxClient.post(url, *args, **kwargs)

    def get(self, api: str, root: str = None, *args, **kwargs):
        url = addr_of_api(api, http_root=root)
        return self.httpxClient.get(url, *args, **kwargs)

    def put(self, api: str, root: str = None, *args, **kwargs):
        url = addr_of_api(api, http_root=root)
        return self.httpxClient.put(url, *args, **kwargs)

    def delete(self, api: str, root: str = None, *args, **kwargs):
        url = addr_of_api(api, http_root=root)
        return self.httpxClient.delete(url, *args, **kwargs)

    def ws_subscribe(self, event_type_name: str):
        """let a function subscribe to ws messages with event type name.
        !!! dfor inner APIs only, do not use this in your code!
        !!! developers should contorl blocking on their own functions

        Args:
            function (Callable): who is subscribing the event type
            event_type_name (str, optional): Which event to listen. Defaults to None.
        """

        def _ws_subscribe(function: Callable):
            self.ws_subscribers[event_type_name].append(function)
            # logger.info(f"ws: {name} subscribed to '{event_type_name}'")
            return function

        return _ws_subscribe

    def check_server_connectivity(self, config=None):
        config = config or get_module_level_config()
        logger.log(f"Connecting to daemon at {config['host']}:{config   ['port']} ...")
        daemon_server_address = f"{config['host']}:{config['port']}"
        http_root = f"http://{daemon_server_address}"

        # check if daemon is alive
        def fetch_hello(root):
            response = None
            try:
                response = self.get(api="hello", root=root)
                assert response.json()["hello"] == "hello"
            except:
                raise IOError(
                    f"Daemon at {root} is not alive: {response.status_code if response else 'no response'}"
                )

        try:
            fetch_hello(http_root)
            logger.ok(f"daemon alive at {http_root}")
            return True
        except Exception as e:
            logger.err(e)
            return False

    def _connect(self, config=None):
        if self.__initialized:
            return  # if already initialized, do nothing

        config = config or get_module_level_config()
        if not config["enable"]:  # check if enable
            self.online_mode = False
            self.__initialized = True
            return

        if not config["allowIpython"]:  # check if allow ipython
            try:
                eval("__IPYTHON__")  # check if in ipython
            except NameError:  # not in ipython
                pass
            else:  # in ipython
                logger.info(
                    "NEETBOX DAEMON won't start when debugging in ipython console. If you want to allow daemon run in "
                    "ipython, try to set 'allowIpython' to True."
                )
                self.online_mode = False
                self.__initialized = True
                return  # ignore if debugging in ipython

        server_host = config["host"]
        server_port = config["port"]
        if not self.check_server_connectivity():  # if daemon not online
            if not (
                is_loopback(server_host) or server_host in ["127.0.0.1"]
            ):  # daemon not running on localhost
                logger.err(
                    RuntimeError(
                        f"No daemon running at {server_host}:{server_port}, daemon will not be attached, stopping..."
                    ),
                    reraise=True,
                )
            # connecting localhost but no server alive, create one
            logger.log(
                f"No daemon running on {server_host}:{server_port}, trying to create daemon..."
            )
            import neetbox.server._daemon_server_launch_script as server_launcher

            popen = DaemonableProcess(  # server daemon
                target=server_launcher,
                args=["--config", json.dumps(config)],
                mode=config["mode"],
                redirect_stdout=subprocess.DEVNULL if config["mute"] else None,
                env_append={"NEETBOX_DAEMON_PROCESS": "1"},
            ).start()
            time.sleep(1)
            _retry_timeout = 10
            _time_begin = time.perf_counter()
            logger.log("Created daemon process, trying to connect to daemon...")
            online_flag = False
            while time.perf_counter() - _time_begin < 10:  # try connect daemon
                if not self.check_server_connectivity():
                    exit_code = popen.poll()
                    if exit_code is not None:
                        logger.err(
                            f"Daemon process exited unexpectedly with exit code {exit_code}."
                        )
                        return False
                    time.sleep(0.5)
                else:
                    online_flag = True
                    break
            if not online_flag:
                logger.err(
                    RuntimeError(
                        f"Failed to connect to daemon after {_retry_timeout}s, stopping..."
                    ),
                    reraise=True,
                )

        self.online_mode = True  # enable online mode
        self.ws_server_url = f"ws://{server_host}:{server_port + 1}"  # ws server url

        logger.log(f"creating websocket connection to {self.ws_server_url}")
        self.wsApp = websocket.WebSocketApp(  # create websocket client
            url=self.ws_server_url,
            on_open=self.on_ws_open,
            on_message=self.on_ws_message,
            on_error=self.on_ws_err,
            on_close=self.on_ws_close,
        )

        Thread(
            target=self.wsApp.run_forever, kwargs={"reconnect": 1}, daemon=True
        ).start()  # initialize and start ws thread

        self.__initialized = True

    def on_ws_open(self, ws: websocket.WebSocketApp):
        project_id = get_project_id()
        logger.ok(f"client websocket connected. sending handshake as '{project_id}'...")
        handshake_msg = EventMsg(  # handshake request message
            project_id=project_id,
            run_id=get_run_id(),
            event_type=EVENT_TYPE_NAME_HANDSHAKE,
            who=IdentityType.CLI,
            event_id=0,
        ).dumps()
        ws.send(handshake_msg)

    def on_ws_err(self, ws: websocket.WebSocketApp, msg):
        logger.err(f"client websocket encountered {msg}")

    def on_ws_close(self, ws: websocket.WebSocketApp, close_status_code, close_msg):
        logger.warn(f"client websocket closed")
        if close_status_code or close_msg:
            logger.warn(f"ws close status code: {close_status_code}")
            logger.warn("ws close message: {close_msg}")
        self.is_ws_connected = False

    def on_ws_message(self, ws: websocket.WebSocketApp, message):
        message = EventMsg.loads(message)  # message should be json
        if message.event_type == EVENT_TYPE_NAME_HANDSHAKE:
            assert message.payload["result"] == 200
            logger.ok(f"handshake succeed.")
            ws.send(  # send immediately without querying
                EventMsg(
                    project_id=get_project_id(),
                    event_id=message.event_id,
                    event_type=EVENT_TYPE_NAME_STATUS,
                    series="config",
                    run_id=get_run_id(),
                    payload=get_module_level_config("@"),
                ).dumps()
            )
            self.is_ws_connected = True
            # return # DO NOT return!
        if message.event_type not in self.ws_subscribers:
            logger.warn(
                f"Client received a(n) {message.event_type} event but nobody subscribes it. Ignoring anyway."
            )
        for subscriber in self.ws_subscribers[message.event_type]:
            try:
                subscriber(message)  # pass payload message into subscriber
            except Exception as e:
                # subscriber throws error
                logger.err(
                    f"Subscriber {subscriber.__name__} crashed on message event {message.event_type}, ignoring."
                )

    def ws_send(
        self,
        event_type: str,
        payload: dict,
        series=None,
        timestamp: str = None,
        event_id=-1,
        _history_len=-1,
    ):
        if not self.__initialized:
            self._connect()
        if self.__initialized and self.online_mode == False:  # if online mode is false
            while len(self.ws_message_query):
                self.ws_message_query.pop()
            return
        message = EventMsg(
            project_id=get_project_id(),
            run_id=get_run_id(),
            event_type=event_type,
            event_id=event_id,
            who=IdentityType.CLI,
            series=series,
            payload=payload,
            timestamp=timestamp or get_timestamp(),
            history_len=_history_len,
        )
        self.ws_message_query.append(message)
        if self.is_ws_connected:  # if ws client exist
            try:
                while len(self.ws_message_query):
                    self.wsApp.send(self.ws_message_query[0].dumps())
                    self.ws_message_query.pop(0)
                return
            except Exception as e:
                pass  # todo what to do


# singleton
connection = NeetboxClient()

# assign this connection to websocket log writer
from neetbox.logging._writer import _assign_connection_to_WebSocketLogWriter

_assign_connection_to_WebSocketLogWriter(connection)


def _clean_websocket_on_exit():
    # clean websocket connection
    if connection.wsApp is not None:
        connection.wsApp.close()


import atexit

atexit.register(_clean_websocket_on_exit)
