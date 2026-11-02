#!/usr/bin/env python3

"""
Nagios/Icinga plugin to monitor WAN connection speed using speedtest-cli

authors:
    Mattia Martinello - mattia@mattiamartinello.com
"""

_VERSION = '1.0.1'
_VERSION_DESCR = 'Nagios/Icinga plugin to monitor WAN connection speed using speedtest-cli'

import argparse
import json
import logging
import sys
import subprocess

ICINGA_OK = 0
ICINGA_WARNING = 1
ICINGA_CRITICAL = 2
ICINGA_UNKNOWN = 3
ICINGA_LABELS = {0: 'OK', 1: 'WARNING', 2: 'CRITICAL', 3: 'UNKNOWN'}

SPEEDTEST_CMD = "speedtest-cli"
SPEEDTEST_TIMEOUT = 120

def icinga_exit(level, details=None, perfdata=None):
    """Exit to system producing an output conform
    to the Icinga standards.
    """
    # build the message as level + details
    msg = ICINGA_LABELS.get(level)
    if details:
        msg = '{} - {}'.format(msg, details)

    # add perfata if given
    if perfdata:
        perfdata_string = ' '.join(perfdata)
        msg = '{} | {}'.format(msg, perfdata_string)

    # exit with status and message: NRPE forwards only stdout
    print(msg, file=sys.stdout)
    sys.exit(level)

def exit_with_error(message):
    """Exit with the Icinga Unknown status code and the given error
    """

    message = 'ERROR: {}'.format(message)
    icinga_exit(ICINGA_UNKNOWN, message)


class IcingaArgumentParser(argparse.ArgumentParser):
    """Argument parser exiting with the Icinga Unknown status code on errors
    (the argparse exit code 2 would mean CRITICAL).
    """

    def error(self, message):
        exit_with_error(message)


class CheckCommand:
    """Parse the command line, run checks and return status.
    """

    def __init__(self):
        # init the cmd line parser
        parser = IcingaArgumentParser(
            description='Icinga plugin: check_speedtest.py'
        )
        self.add_arguments(parser)

        # read the command line
        args = parser.parse_args()

        # manage arguments
        self._manage_arguments(args)

        # Main speedtest command
        self.speedtest_cmd = SPEEDTEST_CMD


    def add_arguments(self, parser):
        """Add command arguments to the argument parser.
        """

        parser.add_argument(
            '-V', '--version',
            action='version',
            version = '%(prog)s v{} - {}'.format(_VERSION, _VERSION_DESCR)
        )

        parser.add_argument(
            '--debug',
            action="store_true",
            help='Print debugging info to console. This may make the plugin '
                 'not working with Icinga since it prints stuff to console.'
        )

        parser.add_argument(
            '--debug2',
            action="store_true",
            help='Print exceptions to console. This may make the plugin'
                 ' not working and get wrong results with Icinga since it'
                 ' prints stuff to console.'
        )

        parser.add_argument(
            '--no-download',
            action="store_true",
            help='Do not perform download test.'
        )

        parser.add_argument(
            '--no-upload',
            action="store_true",
            help='Do not perform upload test.'
        )

        parser.add_argument(
            '--always-ok',
            action="store_true",
            help='Always exit with OK.'
        )

        parser.add_argument(
            '-s', '--server',
            dest='server',
            type=int,
            help='Specify a server ID to test against.'
        )

        parser.add_argument(
            '-w',
            dest='download_warning',
            type=float,
            help='Download warning level in Mbit/s (example: 10 or 10.5).'
        )

        parser.add_argument(
            '-c',
            dest='download_critical',
            type=float,
            help='Download critical level in Mbit/s (example: 2 or 2.5).'
        )

        parser.add_argument(
            '-W',
            dest='upload_warning',
            type=float,
            help='Upload warning level in Mbit/s (example: 2 or 2.5).'
        )

        parser.add_argument(
            '-C',
            dest='upload_critical',
            type=float,
            help='Upload critical level in Mbit/s (example: 1 or 1.5).'
        )

        parser.add_argument(
            '-m',
            dest='download_max',
            type=float,
            help='Maximum download level in Mbit/s for the connection.'
        )

        parser.add_argument(
            '-M',
            dest='upload_max',
            type=float,
            help='Maximum upload level in Mbit/s for the connection.'
        )


    def _manage_arguments(self, args):
        """Get command arguments from the argument parser and load them.
        """

        # debug flag
        self.debug = getattr(args, 'debug', False)
        self.debug2 = getattr(args, 'debug2', False)
        if self.debug or self.debug2:
            logging.basicConfig(level=logging.DEBUG)

        # print arguments (debug)
        logging.debug('Command arguments: {}'.format(args))

        # Do not perform download test
        self.no_download = getattr(args, 'no_download', False)

        # Do not perform upload test
        self.no_upload = getattr(args, 'no_upload', False)

        # Always exit with OK
        self.always_ok = getattr(args, 'always_ok', False)

        # Specify a server ID to test against
        self.server = getattr(args, 'server', None)        

        # Download warning level in Mbit/s
        self.download_warning = getattr(args, 'download_warning', None)
        if self.download_warning is not None:
            logging.debug("Download warning: {}".format(self.download_warning))

        # Download critical level in Mbit/s
        self.download_critical = getattr(args, 'download_critical', None)
        if self.download_critical is not None:
            logging.debug("Download critical: {}".format(
                                                        self.download_critical
                                                        )
            )

        # Upload warning level in Mbit/s
        self.upload_warning = getattr(args, 'upload_warning', None)
        if self.upload_warning is not None:
            logging.debug("Upload warning: {}".format(self.upload_warning))

        # Upload critical level in Mbit/s
        self.upload_critical = getattr(args, 'upload_critical', None)
        if self.upload_critical is not None:
            logging.debug("Upload critical: {}".format(self.upload_critical))

        # Maximum download level in Mbit/s
        self.download_max = getattr(args, 'download_max', None)
        if self.download_max is not None:
            logging.debug("Download max: {}".format(self.download_max))

        # Maximum upload level in Mbit/s
        self.upload_max = getattr(args, 'upload_max', None)
        if self.upload_max is not None:
            logging.debug("Upload max: {}".format(self.upload_max))

        # Arguments checks
        if self.no_download and self.no_upload:
            msg = "You must not specify both --no-download and --no-upload:"
            msg+= " nothing to check!"
            exit_with_error(msg)

        if (
            self.no_download
            and (
                self.download_warning is not None
                or self.download_critical is not None
                or self.download_max is not None
            )
        ):
            msg = "You must not specify download warning, critical or max"
            msg+= " levels if --no-download specified!"
            exit_with_error(msg)

        if (
            self.no_upload
            and (
                self.upload_warning is not None
                or self.upload_critical is not None
                or self.upload_max is not None
            )
        ):
            msg = "You must not specify upload warning, critical or max levels"
            msg+= " if --no-upload specified!"
            exit_with_error(msg)

        if (
            self.download_warning is not None
            and self.download_critical is not None
            and (self.download_warning <= self.download_critical)
        ):
            msg = "Download warning level must be bigger than download"
            msg+= " critical level!"
            exit_with_error(msg)

        if (
            self.upload_warning is not None
            and self.upload_critical is not None
            and (self.upload_warning <= self.upload_critical)
        ):
            msg = "Upload warning level must be bigger than upload"
            msg+= " critical level!"
            exit_with_error(msg)

        # Check download max level
        if (
            self.download_max is not None
            and self.download_critical is not None
        ):
            if (self.download_max < self.download_critical):
                msg = "Download max level cannot be lower than download"
                msg+= " critical level!"
                exit_with_error(msg)

        if self.download_max is not None and self.download_warning is not None:
            if (self.download_max < self.download_warning):
                msg = "Download max level cannot be lower than download"
                msg+= " warning level!"
                exit_with_error(msg)

        # Check upload max level
        if self.upload_max is not None and self.upload_critical is not None:
            if (self.upload_max < self.upload_critical):
                msg = "Upload max level cannot be lower than upload critical"
                msg+= " level!"
                exit_with_error(msg)

        if self.upload_max is not None and self.upload_warning is not None:
            if (self.upload_max < self.upload_warning):
                msg = "Upload max level cannot be lower than upload warning"
                msg+= " level!"
                exit_with_error(msg)


    def _compose_speedtest_command(self):
        # Main speedtest command
        command = [ self.speedtest_cmd, "--json" ]

        # Build command arguments
        if self.no_download:
            command.append("--no-download")

        if self.no_upload:
            command.append("--no-upload")

        if self.server:
            command.append("--server")
            command.append(str(self.server))

        logging.debug("Composed speedtest command: {}".format(command))

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=SPEEDTEST_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            msg = "Speedtest command timed out after {} seconds"
            exit_with_error(msg.format(SPEEDTEST_TIMEOUT))
        except FileNotFoundError:
            msg = "Speedtest command not found: {}"
            exit_with_error(msg.format(self.speedtest_cmd))

        output = result.stdout.decode('utf-8', errors='replace')
        errors = result.stderr.decode('utf-8', errors='replace')
        status = result.returncode

        logging.debug("Speedtest command exited with status {}".format(status))
        logging.debug("Command output: {}".format(output))
        logging.debug("Command errors: {}".format(errors))

        if status != 0:
            msg = "Speedtest command exited with status {}".format(status)
            lines = errors.strip().splitlines()
            if lines:
                msg = "{}: {}".format(msg, lines[-1])
            exit_with_error(msg)

        return output


    def _get_speed(self, result, key):
        # Get a speed in bit/s from the result and convert it to Mbit/s
        value = result.get(key)
        if value is None:
            return None

        try:
            return round(float(value) / 1000000, 2)
        except (TypeError, ValueError):
            msg = "Invalid {} speed in speedtest output: {}"
            exit_with_error(msg.format(key, value))


    def _parse_output(self, output):
        try:
            result = json.loads(output)
        except ValueError as e:
            exit_with_error("Invalid speedtest JSON output: {}".format(e))

        if not isinstance(result, dict):
            exit_with_error("Invalid speedtest JSON output: not an object")

        # A disabled test is reported by speedtest-cli with speed 0: ignore it
        download_speed = None
        if not self.no_download:
            download_speed = self._get_speed(result, 'download')
            if download_speed is None:
                exit_with_error("No download speed in speedtest output")

        logging.debug("Download speed: {}".format(download_speed))
        self.download_speed = download_speed

        upload_speed = None
        if not self.no_upload:
            upload_speed = self._get_speed(result, 'upload')
            if upload_speed is None:
                exit_with_error("No upload speed in speedtest output")

        logging.debug("Upload speed: {}".format(upload_speed))
        self.upload_speed = upload_speed


    def _compose_level_string(self, level=0, print_ok=False, prepend="",
                              left_delimiter="[", right_delimiter="]"):
        # If print OK not enabled and level OK, print an empty string
        if not print_ok and level == 0:
            return ""
        
        # Compose the level string
        if level == 0:
            level_string = "OK"
        elif level == 1:
            level_string = "WARNING"
        elif level == 2:
            level_string = "CRITICAL"
        elif level == 3:
            level_string = "UNKNOWN"

        # Compose the final string
        string = "{}{}{}{}"
        string = string.format(
            prepend,
            left_delimiter,
            level_string,
            right_delimiter
        )

        return string


    def _compose_output_message(self, download_speed, upload_speed,
                                download_result_level=0,
                                upload_result_level=0):
        # Compose download speed output message
        if download_speed is not None:
            result_string = self._compose_level_string(
                level=download_result_level,
                prepend=" "
            )

            download_speed_msg = "Download speed: {} Mbit/sec{}"
            download_speed_msg = download_speed_msg.format(download_speed,
                                                           result_string)
        else:
            download_speed_msg = "No download speed"
        
        # Compose upload speed output message
        if upload_speed is not None:
            result_string = self._compose_level_string(
                level=upload_result_level,
                prepend=" "
            )

            upload_speed_msg = "Upload speed: {} Mbit/sec{}"
            upload_speed_msg = upload_speed_msg.format(upload_speed,
                                                       result_string)
        else:
            upload_speed_msg = "No upload speed"

        # Compose and return final message
        message = "{}, {}".format(download_speed_msg, upload_speed_msg)
        return message
    

    def _compose_perfdata(self,
                          download_speed=None, download_warning=None,
                          download_critical=None, max_download_speed=None,
                          upload_speed=None, upload_warning=None,
                          upload_critical=None, max_upload_speed=None
                         ):
        
        min_value = 0.0

        perfdata = []

        # Download speed
        if download_speed is not None:
            perfdata.append(self._compose_perfdata_string(
                "download_speed", download_speed, download_warning,
                download_critical, min_value, max_download_speed
            ))

        # Upload speed
        if upload_speed is not None:
            perfdata.append(self._compose_perfdata_string(
                "upload_speed", upload_speed, upload_warning,
                upload_critical, min_value, max_upload_speed
            ))

        return perfdata


    def _compose_perfdata_string(self, label, value, warning, critical,
                                 min_value, max_value):
        # Levels are "x:" ranges: the alarm is raised when value falls below x
        has_max = max_value is not None
        perfdata_elements = [
            str(value),
            '{}:'.format(warning) if warning is not None else '',
            '{}:'.format(critical) if critical is not None else '',
            str(min_value) if has_max else '',
            str(max_value) if has_max else ''
        ]
        logging.debug("{} perfdata: {}".format(label, perfdata_elements))

        perfdata_string = ';'.join(perfdata_elements).rstrip(';')
        return "'{}'={}".format(label, perfdata_string)


    def _get_level(self, speed, warning, critical):
        # Speeds are bad when low: compare them with warning and critical
        if speed is None:
            return ICINGA_OK
        if critical is not None and speed < critical:
            return ICINGA_CRITICAL
        if warning is not None and speed < warning:
            return ICINGA_WARNING
        return ICINGA_OK


    def _parse_results(self):
        # Calculate download and upload levels
        download_level = self._get_level(
            self.download_speed,
            self.download_warning,
            self.download_critical
        )
        upload_level = self._get_level(
            self.upload_speed,
            self.upload_warning,
            self.upload_critical
        )

        # If always ok not enabled the worst level is the exit level
        exit_level = ICINGA_OK
        if not self.always_ok:
            exit_level = max(download_level, upload_level)

        # Compose output message
        output_message = self._compose_output_message(
            self.download_speed,
            self.upload_speed,
            download_level,
            upload_level
        )

        # Compose perfdata
        perfdata = self._compose_perfdata(
            download_speed=self.download_speed,
            download_warning=self.download_warning,
            download_critical=self.download_critical,
            max_download_speed=self.download_max,
            upload_speed=self.upload_speed,
            upload_warning=self.upload_warning,
            upload_critical=self.upload_critical,
            max_upload_speed=self.upload_max
        )

        # Exit with level, message and perfdata
        icinga_exit(exit_level, output_message, perfdata)


    def handle(self):
        """Execute the speedtest command, parse the output and give check
        result.
        """

        # Build the speedtest command to be executed
        output = self._compose_speedtest_command()

        # Get download and upload speed
        self._parse_output(output)

        # Parse speeds and exit
        self._parse_results()


if __name__ == "__main__":
    # run the procedure and get results: if I get an exception I exit with
    # the Icinga UNKNOWN status code
    main = CheckCommand()

    if main.debug2:
        main.handle()
    else:
        try:
            main.handle()
        except SystemExit:
            raise
        except Exception as e:
            logging.debug(e.__class__.__name__)
            exit_with_error(e)
