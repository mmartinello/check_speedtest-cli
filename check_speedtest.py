#!/usr/bin/env python3

"""
Nagios/Icinga plugin to monitor WAN connection speed using speedtest-cli

authors:
    Mattia Martinello - mattia@mattiamartinello.com
"""

_VERSION = '1.0'
_VERSION_DESCR = 'Nagios/Icinga plugin to monitor WAN connection speed using speedtest-cli'

import argparse
import logging
import sys
import re
import subprocess

ICINGA_OK = 0
ICINGA_WARNING = 1
ICINGA_CRITICAL = 2
ICINGA_UNKNOWN = 3
ICINGA_LABELS = {0: 'OK', 1: 'WARNING', 2: 'CRITICAL', 3: 'UNKNOWN'}

SPEEDTEST_CMD = "speedtest-cli"

def icinga_exit(level, details=None, perfdata=[]):
    """Exit to system producing an output conform
    to the Icinga standards.
    """
    # choose the right stream
    stream = sys.stdout if level == ICINGA_OK else sys.stderr

    # build the message as level + details
    msg = ICINGA_LABELS.get(level)
    if details:
        msg = '{} - {}'.format(msg, details)

    # add perfata if given
    if len(perfdata):
        perfdata_string = ' '.join(perfdata)
        msg = '{} |{}'.format(msg, perfdata_string)

    # exit with status and message
    print(msg, file=stream)
    sys.exit(level)

def exit_with_error(message):
    """Exit with the Icinga Unknown status code and the given error
    """

    message = 'ERROR: {}'.format(message)
    icinga_exit(ICINGA_UNKNOWN, message)


class CheckCommand:
    """Parse the command line, run checks and return status.
    """

    def __init__(self):
        # init the cmd line parser
        parser = argparse.ArgumentParser(
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
            help='Download warning level in Mbit/s (example: 10 or 10.5).'
        )

        parser.add_argument(
            '-c',
            dest='download_critical',
            help='Download critical level in Mbit/s (example: 2 or 2.5).'
        )

        parser.add_argument(
            '-W',
            dest='upload_warning',
            help='Upload warning level in Mbit/s (example: 2 or 2.5).'
        )

        parser.add_argument(
            '-C',
            dest='upload_critical',
            help='Upload critical level in Mbit/s (example: 1 or 1.5).'
        )

        parser.add_argument(
            '-m',
            dest='download_max',
            help='Maximum download level in Mbit/s for the connection.'
        )

        parser.add_argument(
            '-M',
            dest='upload_max',
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
        if self.download_warning:
            self.download_warning = float(self.download_warning)
            logging.debug("Download warning: {}".format(self.download_warning))

        # Download critical level in Mbit/s
        self.download_critical = getattr(args, 'download_critical', None)     
        if self.download_critical:
            self.download_critical = float(self.download_critical)
            logging.debug("Download critical: {}".format(
                                                        self.download_critical
                                                        )
            )

        # Upload warning level in Mbit/s
        self.upload_warning = getattr(args, 'upload_warning', None)        
        if self.upload_warning:
            self.upload_warning = float(self.upload_warning)
            logging.debug("Upload warning: {}".format(self.upload_warning))

        # Upload critical level in Mbit/s
        self.upload_critical = getattr(args, 'upload_critical', None)     
        if self.upload_critical:
            self.upload_critical = float(self.upload_critical)
            logging.debug("Upload critical: {}".format(self.upload_critical))

        # Maximum download level in Mbit/s
        self.download_max = getattr(args, 'download_max', None)
        if self.download_max:
            self.download_max = float(self.download_max)
            logging.debug("Download max: {}".format(self.download_max))

        # Maximum upload level in Mbit/s
        self.upload_max = getattr(args, 'upload_max', None)  
        if self.upload_max:
            self.upload_max = float(self.upload_max)
            logging.debug("Upload max: {}".format(self.upload_max))

        # Arguments checks
        if (
            self.no_download
            and (
                self.download_warning
                or self.download_critical
                or self.download_max
            )
        ):
            msg = "You must not specify download warning, critical or max"
            msg+= " levels if --no-download specified!"
            exit_with_error(msg)

        if (
            self.no_upload
            and (
                self.upload_warning
                or self.upload_critical
                or self.upload_max
            )
        ):
            msg = "You must not specify upload warning, critical or max levels"
            msg+= " if --no-upload specified!"
            exit_with_error(msg)

        if (
            self.download_warning and self.download_critical
            and (self.download_warning <= self.download_critical)
        ):
            msg = "Download warning level must be bigger than download"
            msg+= " critical level!"
            exit_with_error(msg)

        if (
            self.upload_warning and self.upload_critical
            and (self.upload_warning <= self.upload_critical)
        ):
            msg = "Upload warning level must be bigger than upload"
            msg+= " critical level!"
            exit_with_error(msg)

        # Check download max level
        if self.download_max:
            if (self.download_max < self.download_critical):
                msg = "Download max level cannot be lower than download"
                msg+= " critical level!"
                exit_with_error(msg)

            if (self.download_max < self.download_warning):
                msg = "Download max level cannot be lower than download"
                msg+= " warning level!"
                exit_with_error(msg)

        # Check upload max level
        if self.upload_max:
            if (self.upload_max < self.upload_critical):
                msg = "Upload max level cannot be lower than upload critical"
                msg+= " level!"
                exit_with_error(msg)

            if (self.upload_max < self.upload_warning):
                msg = "Upload max level cannot be lower than upload warning"
                msg+= " level!"
                exit_with_error(msg)


    def _compose_speedtest_command(self):
        # Main speedtest command
        command = [ self.speedtest_cmd ]

        # Build command arguments
        if self.no_download:
            command.append("--no-download")

        if self.no_upload:
            command.append("--no-upload")

        if self.server:
            command.append("--server")
            command.append(self.server)

        logging.debug("Composed speedtest command: {}".format(command))

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        output = result.stdout.decode('utf-8')
        status = result.returncode

        logging.debug("Speedtest command exited with status {}".format(status))
        logging.debug("Command output: {}".format(output))

        return output


    def _parse_output(self, output):
        # Match the output to get download speed
        try:
            matches = re.search(
                "^Download: (.+) Mbit\/s$",
                output,
                re.MULTILINE
            )
            download_speed = matches.group(1)
            download_speed = float(download_speed)
        except:
            download_speed = None

        logging.debug("Download speed: {}".format(download_speed))
        self.download_speed = download_speed


        # Match the output to get upload speed
        try:
            matches = re.search(
                "^Upload: (.+) Mbit\/s$",
                output,
                re.MULTILINE
            )
            upload_speed = matches.group(1)
            upload_speed = float(upload_speed)
        except:
            upload_speed = None

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
        if download_speed:
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
        if download_speed:
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
        
        null_value = 'NaN'
        min_value = 0.0

        perfdata = []
        
        # Download speed
        label = "download_speed"
        
        value = null_value
        if download_speed:
            value = '{}Mbit/sec'.format(str(download_speed))

        perfdata_elements = [
            value,
            str(download_warning) if download_warning else null_value,
            str(download_critical) if download_critical else null_value,
            str(min_value) if max_upload_speed else null_value,
            str(max_download_speed) if max_download_speed else null_value
        ]
        logging.debug("Download perfdata: {}".format(perfdata_elements))
        perfdata_string = "'{}'={}".format(label, ';'.join(perfdata_elements))
        perfdata.append(perfdata_string)

        # Upload speed
        label = "upload_speed"

        value = null_value
        if upload_speed:
            value = '{}Mbit/sec'.format(str(upload_speed))

        perfdata_elements = [
            value,
            str(upload_warning) if upload_warning else null_value,
            str(upload_critical) if upload_critical else null_value,
            str(min_value) if max_upload_speed else null_value,
            str(max_upload_speed) if max_upload_speed else null_value
        ]
        logging.debug("Upload perfdata: {}".format(perfdata_elements))
        perfdata_string = "'{}'={}".format(label, ';'.join(perfdata_elements))
        perfdata.append(perfdata_string)

        return perfdata


    def _parse_results(self):
        # Exit if no download and upload speed recognised
        if not self.download_speed and not self.upload_speed:
            exit_with_error("No download and upload speed recognised")

        # Set default levels
        exit_level = 0
        download_level = 0
        upload_level = 0

        # Check the download warning level

        # If always ok not enabled check results and calculate exit level
        if not self.always_ok:
            if (
                self.download_warning
                and self.download_speed < self.download_warning
            ):
                exit_level = 1
                download_level = 1

            # Check the upload warning level
            if (
                self.upload_warning
                and self.upload_speed < self.upload_warning
            ):
                exit_level = 1
                upload_level = 1

            # Check the download critical level
            if (
                self.download_critical
                and self.download_speed < self.download_critical
            ):
                exit_level = 2
                download_level = 2

            # Check the upload critical level
            if (
                self.upload_critical
                and self.upload_speed < self.upload_critical
            ):
                exit_level = 2
                upload_level = 2

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
        except Exception as e:
            logging.debug(e.__class__.__name__)
            exit_with_error(e)
