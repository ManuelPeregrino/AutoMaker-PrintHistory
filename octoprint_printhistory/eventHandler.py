# coding=utf-8

__author__ = "Jarek Szczepanski <imrahil@imrahil.com>"
__license__ = "GNU Affero General Public License http://www.gnu.org/licenses/agpl.html"
__copyright__ = "Copyright (C) 2014 Jarek Szczepanski - Released under terms of the AGPLv3 License"

def eventHandler(self, event, payload):
    from octoprint.events import Events
    import json
    import time
    from operator import itemgetter
    from .parser import UniversalParser

    import sqlite3

    supported_event = None

    # support for print done & cancelled events
    if event == Events.PRINT_DONE:
        supported_event = event

    elif event == Events.PRINT_FAILED:
        supported_event = event

    elif event == Events.METADATA_STATISTICS_UPDATED:
        supported_event = event

    # unsupported event
    if supported_event is None:
        return

    if supported_event is not Events.METADATA_STATISTICS_UPDATED:
        self._logger.info("Name: "+ payload["name"])
        self._logger.info("Origin: "+ payload["origin"])
        self._logger.info("Path: "+ payload["path"])
        self._logger.info("Path_On_disk: "+ self._file_manager.path_on_disk(payload["origin"], payload["path"]))
        try:
            fileData = self._file_manager.get_metadata(payload["origin"], payload["name"])
            self._logger.info("Got metadata from name")
        except:
            self._logger.info("Error getting metadata from name, trying with path")
            try:
                fileData = self._file_manager.get_metadata(payload["origin"], payload["path"])
            except:
                self._logger.info("Error getting metadata from name and path, terminating")
                fileData = None

        fileName = payload["name"]

        if fileData is None:
          self._logger.info("FileData came out empty, trying to get it from path")
          fileData = self._file_manager.get_metadata(payload["origin"], payload["path"])


        if fileData is not None:
            self._logger.info("found fileData")
            timestamp = 0
            success = None
            estimatedPrintTime = 0
            gcode_parser = UniversalParser(self._file_manager.path_on_disk(payload["origin"], payload["path"]), logger=self._logger)
            parameters = gcode_parser.parse()
            currentFile = {
                "fileName": fileName,
                "note": "",
                "parameters": json.dumps(parameters)
            }
            self._logger.info(json.dumps(parameters))
            # analysis - looking for info about filament usage
            if "analysis" in fileData:
                if "filament" in fileData["analysis"]:
                    if "tool0" in fileData["analysis"]["filament"]:
                        filamentVolume = fileData["analysis"]["filament"]["tool0"]["volume"]
                        filamentLength = fileData["analysis"]["filament"]["tool0"]['length']

                        currentFile["filamentVolume"] = filamentVolume if filamentVolume is not None else 0
                        currentFile["filamentLength"] = filamentLength if filamentLength is not None else 0

                    if "tool1" in fileData["analysis"]["filament"]:
                        filamentVolume = fileData["analysis"]["filament"]["tool1"]["volume"]
                        filamentLength = fileData["analysis"]["filament"]["tool1"]['length']

                        currentFile["filamentVolume2"] = filamentVolume if filamentVolume is not None else 0
                        currentFile["filamentLength2"] = filamentLength if filamentLength is not None else 0

                    estimatedPrintTime = fileData["analysis"]["estimatedPrintTime"] if "estimatedPrintTime" in fileData["analysis"] else 0

                    # Temporarily disabled
                    # if "tool0" in fileData["analysis"]["filament"] and "tool1" in fileData["analysis"]["filament"]:
                    #     currentFile["note"] = "Dual extrusion"

            # make sure we have zeroes for these values if not set above
            if not currentFile.get("filamentVolume"):
                currentFile["filamentVolume"] = 0

            if not currentFile.get("filamentLength"):
                currentFile["filamentLength"] = 0

            # how long print took
            if "time" in payload:
                currentFile["printTime"] = payload["time"]
            else:
                printTime = self._comm.getPrintTime() if self._comm is not None else ""
                currentFile["printTime"] = printTime

            if "owner" in payload:
                currentFile["user"] = payload["user"]
            else:
                currentFile["user"] = ""


            # when print happened and what was the result
            if "history" in fileData:
                history = fileData["history"]

                newlist = sorted(history, key=itemgetter('timestamp'), reverse=True)

                if newlist:
                    last = newlist[0]

                    success = last["success"]

            if not success:
                success = False if event == Events.PRINT_FAILED else True

            timestamp = int(time.time())

            currentFile["success"] = success
            currentFile["timestamp"] = timestamp

            self._history_dict = None

            conn = sqlite3.connect(self._history_db_path)
            cur  = conn.cursor()
            cur.execute("INSERT INTO print_history (fileName, note, filamentVolume, filamentLength, printTime, success, timestamp, user, parameters) VALUES (:fileName, :note, :filamentVolume, :filamentLength, :printTime, :success, :timestamp, :user, :parameters)", currentFile)
            conn.commit()
            conn.close()

    else:
        # sometimes Events.PRINT_DONE is fired BEFORE metadata.yaml is updated - we have to wait for Events.METADATA_STATISTICS_UPDATED and update database
        self._logger.info("fileData not found")
        try:
            fileData = self._file_manager.get_metadata(payload["storage"], payload["path"])
        except:
            fileData = None

        if "history" in fileData:
            history = fileData["history"]

            newlist = sorted(history, key=itemgetter('timestamp'), reverse=True)

            if newlist:
                last = newlist[0]

                success = last["success"]
                timestamp = int(last["timestamp"])

                conn = sqlite3.connect(self._history_db_path)
                cur = conn.cursor()
                cur.execute("UPDATE print_history SET success = ? WHERE timestamp = ?", (success, timestamp))
                conn.commit()
                conn.close()

