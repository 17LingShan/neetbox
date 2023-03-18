# -*- coding: utf-8 -*-
#
# Author: GavinGong aka VisualDust
# URL:    https://gong.host
# Date:   20230315

import getpass
import inspect
import os, re
import platform
from datetime import date, datetime
from enum import Enum
from neetbox.core.framing import *
from neetbox.logging.formatting import *


class LogLevel(Enum):
    ALL = 3
    WARNING = 2
    DEBUG = 1
    ERROR = 0

    def __lt__(self, other):
        return self.value < other.value

    def __le__(self, other):
        return self.value <= other.value

    def __eq__(self, other):
        return self.value == other.value

    def __ne__(self, other):
        return self.value != other.value

    def __gt__(self, other):
        return self.value > other.value

    def __ge__(self, other):
        return self.value >= other.value


writers_dict = {}
style_dict = {}
loggers_dict = {}

_global_log_level = LogLevel.ALL


def set_log_level(level: LogLevel):
    if type(level) is int:
        assert level >= 0 and level <= 3
        level = LogLevel(level)
    _global_log_level = level


class Logger:
    def __init__(self, whom, style: LogStyle = None):
        self.whom: any = whom
        self.style: LogStyle = style
        self.file_writer = None

    def log(
        self,
        *content,
        prefix: str = None,
        datetime_format: str = None,
        with_identifier: bool = None,
        with_datetime: bool = None,
        into_file: bool = True,
        into_stdout: bool = True,
    ):
        _caller_identity = get_caller_identity_traceback(traceback=2)

        # getting style
        _style = self.style
        if not _style:  # if style not set
            _style_index = str(_caller_identity)
            if _style_index in style_dict:  # check for previous style
                _style = style_dict[_style_index]
            else:
                _style = LogStyle().randcolor()
                style_dict[_style_index] = _style

        # composing prefix
        _prefix = _style.prefix
        if prefix is not None:  # if using specific prefix
            _prefix = prefix

        # composing datetime
        _with_datetime = _style.with_datetime
        _datetime = ""
        if (
            with_datetime is not None
        ):  # if explicitly determined wether to log with datetime
            _with_datetime = with_datetime
        if _with_datetime:
            _datetime_fmt = (
                datetime_format if datetime_format else _style.datetime_format
            )
            _datetime = datetime.now().strftime(_datetime_fmt)

        # if with identifier
        _whom = ""
        _with_identifier = _style.with_identifier
        if (
            with_identifier is not None
        ):  # if explicitly determined wether to log with identifier
            _with_identifier = with_identifier
        if _with_identifier:
            _whom = self.whom  # check identity
            if _whom is None:  # if using default logger, tracing back to the caller
                _whom = ""
                if (
                    _caller_identity.module and _style.trace_level >= 2
                ):  # trace as module level
                    _whom += _caller_identity.module + _style.split_char_identity
                if (
                    _caller_identity.class_name and _style.trace_level >= 1
                ):  # trace as class level
                    _whom += (
                        _caller_identity.class_name + _style.split_char_identity
                    )
                if (
                    _whom is None and _style.trace_level >= 1
                ):  # not module level and class level
                    _whom = _caller_identity.filename + _style.split_char_identity
                if _caller_identity.func_name != "<module>":  # skip for jupyters
                    _whom += _caller_identity.func_name

        # converting args into a single string
        _message = ""
        for msg in content:
            _message += str(msg)

        # perform log
        if into_stdout:
            print(
                _prefix
                + _datetime
                + _style.split_char_cmd
                + colored_by_style(_whom, style=_style)
                + _style.split_char_cmd
                + _message
            )
        if into_file and self.file_writer is not None:
            self.file_writer.write(
                _prefix
                + _datetime
                + _style.split_char_txt
                + _whom
                + _style.split_char_txt
                + _message
            )
        return self

    def debug(self, info, flag=f"DEBUG"):
        if _global_log_level <= LogLevel.DEBUG.value:
            self.log(info, prefix=f"[{colored(flag, AnsiColor.CYAN)}]", into_file=False)
            self.log(info, prefix=flag, into_stdout=False)
        return self

    def ok(self, message, flag="OK"):
        self.log(message, prefix=f"[{colored(flag, AnsiColor.GREEN)}]", into_file=False)
        self.log(message, prefix=flag, into_stdout=False)
        return self

    def warn(self, message, flag="WARNING"):
        self.log(
            message, prefix=f"[{colored(flag, AnsiColor.YELLOW)}]", into_file=False
        )
        self.log(message, prefix=flag, into_stdout=False)
        return self

    def err(self, err, flag="ERROR"):
        self.log(err, prefix=f"[{colored(flag,AnsiColor.RED)}]", into_file=False)
        self.log(err, prefix=flag, into_stdout=False)
        return self

    def log_os_info(self):
        """Log some maybe-useful os info

        Returns:
            _Logger : the logger instance itself
        """
        message = (
            f"whom\t\t|\t" + getpass.getuser() + " using " + str(platform.node()) + "\n"
        )
        message += (
            "machine\t\t|\t"
            + str(platform.machine())
            + " on "
            + str(platform.processor())
            + "\n"
        )
        message += (
            "system\t\t|\t" + str(platform.system()) + str(platform.version()) + "\n"
        )
        message += (
            "python\t\t|\t"
            + str(platform.python_build())
            + ", ver "
            + platform.python_version()
            + "\n"
        )
        self.log(
            message=message,
            with_identifier=False,
            prefix=None,
            with_ic=False,
            date_time_fmt=False,
            method_level=False,
        )
        return self

    def skip_lines(self, line_cnt=1):
        """Let the logger log some empty lines

        Args:
            line_cnt (int, optional): how many empty line. Defaults to 1.

        Returns:
            _Logger : the logger instance itself
        """
        self.log(
            message="\n" * line_cnt,
            prefix=None,
            with_ic=False,
            date_time_fmt=False,
            method_level=False,
        )
        return self

    def log_txt_file(self, file):
        if isinstance(file, str):
            file = open(file)
        context = ""
        for line in file.readlines():
            context += line
        self.log(
            message=context,
            prefix=None,
            with_identifier=False,
            with_ic=False,
            date_time_fmt=False,
            method_level=False,
        )
        return self

    def set_log_dir(self, path, independent=False):
        if os.path.isfile(path):
            raise "Target path is not a directory."
        if not os.path.exists(path):
            static_logger.log(f"Directory {path} not found, trying to create.")
            try:
                os.makedirs(path)
            except:
                static_logger.log(f"Failed when trying to create directory {path}")
                raise Exception(f"Failed when trying to create directory {path}")
        log_file_name = ""
        if independent:
            log_file_name += self.whom
        log_file_name += str(date.today()) + ".log"
        self.bind_file(os.path.join(path, log_file_name))
        return self

    def bind_file(self, path):
        log_file_identity = os.path.abspath(path)
        if os.path.isdir(log_file_identity):
            raise Exception("Target path is not a file.")
        filename = validateTitle(os.path.basename(path))
        dirname = os.path.dirname(path) if len(os.path.dirname(path)) != 0 else "."
        if not os.path.exists(dirname):
            raise Exception(f"Could not find dictionary {dirname}")
        real_path = os.path.join(dirname, filename)
        if log_file_identity not in writers_dict:
            writers_dict[log_file_identity] = open(real_path, "a", buffering=1)
        self.file_writer = writers_dict[log_file_identity]
        return self

    def file_bend(self) -> bool:
        return self.file_writer == None


DEFAULT_LOGGER = Logger(None)


def get_logger(whom: any = None, icon=None, style: LogStyle = None) -> Logger:
    if whom is None:
        return DEFAULT_LOGGER
    if whom in loggers_dict:
        return loggers_dict[whom]
    loggers_dict[whom] = Logger(whom=whom, style=style)
    return loggers_dict[whom]


def validateTitle(text: str):
    """Remove invalid characters for windows file systems

    Args:
        title (str): the given title

    Returns:
        str: valid text
    """
    if platform.system().lower() == "windows":
        rstr = r"[\/\\\:\*\?\"\<\>\|]"  # '/ \ : * ? " < > |'
        new_title = re.sub(rstr, "_", text)  # replace with '_'
        return new_title
    return text