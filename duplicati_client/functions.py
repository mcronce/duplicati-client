import yaml

from . import common
from . import helper
from .requests_wrapper import requests_wrapper as requests

# Function for display a list of resources
def list_resources(data, resource):
    common.verify_token(data)

    if resource == "backups":
        resource_list = fetch_backup_list(data)
    elif resource == "databases":
        resource_list = fetch_database_list(data)
    else:
        resource_list = fetch_resource_list(data, resource)

    resource_list = list_filter(resource_list, resource)

    if len(resource_list) == 0:
        common.log_output("No items found", True)
        sys.exit(2)

    # Must use safe_dump for python 2 compatibility
    message = yaml.safe_dump(resource_list, default_flow_style=False)
    common.log_output(message, True, 200)


# Fetch all backups
def fetch_backup_list(data):
    backups = fetch_resource_list(data, "backups")

    # Fetch progress state
    progress_state, active_id = fetch_progress_state(data)
    progress = progress_state.get("OverallProgress", 1)

    backup_list = []
    for backup in backups:
        backup_id = backup.get("Backup", {}).get("ID", 0)
        if active_id is not None and backup_id == active_id and progress != 1:
            backup["Progress"] = progress_state
        backup_list.append(backup)

    return backup_list


# Fetch all databases
def fetch_database_list(data):
    databases = fetch_resource_list(data, "backups")

    database_list = []
    for backup in databases:
        db_path = backup.get("Backup", {}).get("DBPath", "")
        db_exists = validate_database_exists(data, db_path)
        database = {
            "Backup": backup.get("Backup", {}).get("Name", 0),
            "DBPath": db_path,
            "ID": backup.get("Backup", {}).get("ID", 0),
            "Exists": db_exists
        }
        database_list.append(database)

    return database_list


# Validate that the database exists on the server
def validate_database_exists(data, db_path):
    common.verify_token(data)

    # api/v1/filesystem/validate
    baseurl = common.create_baseurl(data, "/api/v1/filesystem/validate")
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    payload = {'path': db_path}
    verify = data.get("server", {}).get("verify", True)
    r = requests.post(baseurl, headers=headers, params=payload,
                      cookies=cookies, verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code != 200:
        return False
    return True


# Fetch all resources of a certain type
def fetch_resource_list(data, resource):
    baseurl = common.create_baseurl(data, "/api/v1/" + resource)
    common.log_output("Fetching " + resource + " list from API...", False)
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    r = requests.get(baseurl, headers=headers, cookies=cookies, verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code == 404:
        common.log_output("No entries found", True, r.status_code)
        sys.exit(2)
    elif r.status_code != 200:
        common.log_output("Error connecting", True, r.status_code)
        sys.exit(2)
    else:
        return r.json()


# Filter logic for the list function to facilitate readable output
def list_filter(json_input, resource):
    resource_list = []
    if resource == "backups":
        for key in json_input:
            backup = key.get("Backup", None)
            schedule = key.get("Schedule", None)
            progress_state = key.get("Progress", None)
            backup_name = backup.get("Name", "")
            backup = {
                backup_name: {
                    "ID": backup.get("ID", ""),
                }
            }

            if backup.get('Metadata', {}).get('SourceSizeString') is not None:
                size = backup.get('Metadata', {}).get('SourceSizeString')
                backup[backup_name]["Source size"] = size

            if schedule is not None:
                next_run = helper.format_time(schedule.get("Time", ""))
                if next_run is not None:
                    backup[backup_name]["Next run"] = next_run

                last_run = helper.format_time(schedule.get("LastRun", ""))
                if last_run is not None:
                    backup[backup_name]["Last run"] = last_run

            if progress_state is not None:
                backup[backup_name]["Running"] = {
                    "Task ID": progress_state.get("TaskID", None),
                    "State": progress_state.get("Phase", None),
                }

            resource_list.append(backup)

    elif resource == "notifications":
        for val in json_input:
            notification = {
                val.get("Title", ""): {
                    "Backup ID": val.get("BackupID", ""),
                    "Notification ID": val.get("ID", ""),
                }
            }
            timestamp = helper.format_time(val.get("Timestamp", ""))
            if timestamp is not None:
                notification["Timestamp"] = timestamp

            resource_list.append(notification)

    elif resource == "serversettings":
        for key, value in json_input.items():
            hidden_values = [
                "update-check-latest",
                "last-update-check",
                "is-first-run",
                "update-check-interval",
                "server-passphrase",
                "server-passphrase-salt",
                "server-passphrase-trayicon",
                "server-passphrase-trayicon-hash",
                "unacked-error",
                "unacked-warning",
                "has-fixed-invalid-backup-id",
            ]
            if key in hidden_values:
                continue
            setting = {
                key: {
                    "value": value
                }
            }

            resource_list.append(setting)
    else:
        resource_list = json_input

    return resource_list


# Get one or more resources with somewhat limited fields
def get_resources(data, resource_type, resource_ids):
    if resource_type == "backup":
        result = fetch_backups(data, resource_ids, "get")
    elif resource_type == "notification":
        result = fetch_notifications(data, resource_ids, "get")

    message = yaml.safe_dump(result, default_flow_style=False)
    common.log_output(message, True, 200)


# Get one or more resources with all fields
def describe_resources(data, resource_type, resource_ids):
    if resource_type == "backup":
        result = fetch_backups(data, resource_ids, "describe")
    elif resource_type == "notification":
        result = fetch_notifications(data, resource_ids, "describe")

    # Must use safe_dump for python 2 compatibility
    message = yaml.safe_dump(result, default_flow_style=False)
    common.log_output(message, True, 200)


# Fetch notifications
def fetch_notifications(data, notification_ids, method):
    common.verify_token(data)

    common.log_output("Fetching notifications from API...", False)
    baseurl = common.create_baseurl(data, "/api/v1/notifications")
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    notification_list = []
    r = requests.get(baseurl, headers=headers, cookies=cookies, verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code != 200:
        id_list = ', '.join(notification_ids)
        message = "Error getting notifications " + id_list
        common.log_output(message, True, r.status_code)
    else:
        data = r.json()

    for notification in data:
        notification_id = notification.get("ID", -1)
        if notification_id in notification_ids:
            notification_list.append(notification)

    # Only get uses a filter
    if method == "get":
        notification_list = notification_filter(notification_list)

    return notification_list


# Filter logic for the notification get command
def notification_filter(json_input):
    notification_list = []
    for key in json_input:
        title = key.get("Title", "Notification")
        notification = {
            title: {
                "Backup ID": key.get("BackupID", ""),
                "Notification ID": key.get("ID", ""),
                "Message": key.get("Message", ""),
                "Type": key.get("Type", ""),
            }
        }
        timestamp = helper.format_time(key.get("Timestamp", ""))
        if timestamp is not None:
            notification[title]["Timestamp"] = timestamp

        notification_list.append(notification)

    return notification_list


# Fetch backups
def fetch_backups(data, backup_ids, method):
    common.verify_token(data)

    common.log_output("Fetching backups from API...", False)
    progress_state, active_id = fetch_progress_state(data)
    progress = progress_state.get("OverallProgress", 1)
    backup_list = []
    baseurl = common.create_baseurl(data, "/api/v1/backup/")
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    # Iterate over backup_ids and fetch their info
    for backup_id in backup_ids:
        r = requests.get(baseurl + str(backup_id), headers=headers,
                         cookies=cookies, verify=verify)
        common.check_response(data, r.status_code)
        if r.status_code != 200:
            message = "Error getting backup " + str(backup_id)
            common.log_output(message, True, r.status_code)
            continue
        backup = r.json()["data"]

        item_id = backup.get("Backup", {}).get("ID", 0)
        if active_id is not None and item_id == active_id and progress != 1:
            backup["Progress"] = progress_state

        backup_list.append(backup)

    if len(backup_list) == 0:
        sys.exit(2)

    # Only get uses a filter
    if method == "get":
        backup_list = backup_filter(backup_list)

    return backup_list


# Fetch backup progress state
def fetch_progress_state(data):
    baseurl = common.create_baseurl(data, "/api/v1/progressstate")
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    # Check progress state and get info for the running backup
    r = requests.get(baseurl, headers=headers, cookies=cookies, verify=verify)
    if r.status_code != 200:
        active_id = -1
        progress_state = {}
    else:
        progress_state = r.json()
        active_id = progress_state.get("BackupID", -1)

    # Don't show progress on finished tasks
    phase = progress_state.get("Phase", "")
    if phase in ["Backup_Complete", "Error"]:
        return {}, 0

    return progress_state, active_id


# Filter logic for the fetch backup/backups methods
def backup_filter(json_input):
    backup_list = []
    for key in json_input:
        backup = key.pop("Backup", {})
        metadata = backup.pop("Metadata", {})
        backup_name = backup.pop("Name", {})
        backup = {
            "ID": backup.get("ID", ""),
            "Local database": backup.get("DBPath", ""),
        }
        backup["Versions"] = int(metadata.get("BackupListCount", 0))
        backup["Last run"] = {
            "Duration":
            helper.format_duration(metadata.get("LastBackupDuration", "0")),
            "Started":
            helper.format_time(metadata.get("LastBackupStarted", "0")),
            "Stopped":
            helper.format_time(metadata.get("LastBackupFinished", "0")),
        }
        backup["Size"] = {
            "Local": metadata.get("SourceSizeString", ""),
            "Backend": metadata.get("TargetSizeString", "")
        }

        schedule = key.get("Schedule", None)
        if schedule is not None:
            next_run = helper.format_time(schedule.pop("Time", ""))
            if next_run is not None:
                schedule["Next run"] = next_run
            last_run = helper.format_time(schedule.pop("LastRun", ""))
            if last_run is not None:
                schedule["Last run"] = last_run
            schedule.pop("AllowedDays", None)
            schedule.pop("ID", None)
            schedule.pop("Rule", None)
            schedule.pop("Tags", None)
            backup["Schedule"] = schedule

        progress_state = key.get("Progress", None)
        if progress_state is not None:
            state = progress_state.get("Phase", None)
            speed = progress_state.get("BackendSpeed", 0)
            progress = {
                "State": state,
                "Counting files": progress_state.get("StillCounting", False),
                "Backend": {
                    "Action": progress_state.get("BackendAction", 0)
                },
                "Task ID": progress_state.get("TaskID", -1),
            }
            if speed > 0:
                readable_speed = helper.format_bytes(speed) + "/s"
                progress["Backend"]["Speed"] = readable_speed

            # Display item only if relevant
            if not progress_state.get("StillCounting", False):
                progress.pop("Counting files")
            # Avoid 0 division
            file_count = progress_state.get("ProcessedFileCount", 0)
            total_file_count = progress_state.get("TotalFileCount", 0)
            processing = state == "Backup_ProcessingFiles"
            if file_count > 0 and total_file_count > 0 and processing:
                processed = "{0:.2f}".format(file_count /
                                             total_file_count * 100)
                progress["Processed files"] = processed + "%"
            # Avoid 0 division
            data_size = progress_state.get("ProcessedFileSize", 0)
            total_data_size = progress_state.get("TotalFileSize", 0)
            processing = state == "Backup_ProcessingFiles"
            if data_size > 0 and total_data_size > 0 and processing:
                # Calculate percentage
                processed = "{0:.2f}".format(data_size / total_data_size * 100)
                # Format text "x% (y GB of z GB)"
                processed += "% (" + str(helper.format_bytes(data_size))
                processed += " of "
                processed += str(helper.format_bytes(total_data_size)) + ")"
                progress["Processed data"] = processed
            # Avoid 0 division
            current = progress_state.get("BackendFileProgress", 0)
            total = progress_state.get("BackendFileSize", 0)
            if current > 0 and total > 0:
                backend_progress = "{0:.2f}".format(current / total * 100)
                progress["Backend"]["Progress"] = backend_progress + "%"
            backup["Progress"] = progress

        key = {
            backup_name: backup
        }
        backup_list.append(key)

    return backup_list


# Dimiss notifications
def dismiss_notifications(data, resource_id="all"):
    common.verify_token(data)

    id_list = []
    if resource_id == "all":
        # Get all notification ID's
        notifications = fetch_resource_list(data, "notifications")
        for notification in notifications:
            id_list.append(notification["ID"])
    else:
        id_list.append(resource_id)

    if len(id_list) == 0:
        common.log_output("No notifications", True)
        return

    for item in id_list:
        delete_resource(data, "notification", item, True)


# Fetch logs
def get_logs(data, log_type, backup_id, remote=False,
             follow=False, lines=10, show_all=False):
        common.verify_token(data)

        if log_type == "backup" and backup_id is None:
            common.log_output("A backup id must be provided with --id", True)
            sys.exit(2)

        # Treating functions as objects to allow any function to be "followed"
        if log_type == "backup" and remote:
            def function():
                get_backup_logs(data, backup_id, "remotelog", lines, show_all)
        elif log_type == "backup" and not remote:
            def function():
                get_backup_logs(data, backup_id, "log", lines, show_all)
        elif log_type in ["profiling", "information", "warning", "error"]:
            def function():
                get_live_logs(data, log_type, lines)
        elif log_type == "stored":
            def function():
                get_stored_logs(data, lines, show_all)

        # Follow the function or just run it once
        if follow:
            follow_function(function, 10)
        else:
            function()


# Get local and remote backup logs
def get_backup_logs(data, backup_id, log_type, page_size=5, show_all=False):
    endpoint = "/api/v1/backup/" + str(backup_id) + "/" + log_type
    baseurl = common.create_baseurl(data, endpoint)
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    params = {'pagesize': page_size}

    r = requests.get(baseurl, headers=headers, cookies=cookies, params=params,
                     verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code == 500:
        message = "Error getting log, "
        message += "database may be locked by backup"
        common.log_output(message, True)
        return
    elif r.status_code != 200:
        common.log_output("Error getting log", True, r.status_code)
        return

    result = r.json()[-page_size:]
    logs = []
    for log in result:
        if log.get("Operation", "") == "list":
            log["Data"] = "Expunged"
        else:
            log["Data"] = json.loads(log.get("Data", "{}"))
            size = helper.format_bytes(log["Data"].get("Size", 0))
            log["Data"]["Size"] = size

        if log.get("Message", None) is not None:
            log["Message"] = log["Message"].split("\n")
            message_length = len(log["Message"])
            if message_length > 15 and not show_all:
                log["Message"] = log["Message"][:15]
                lines = str(message_length - 15)
                hidden_message = lines + " hidden lines (show with --all)"
                log["Message"].append(hidden_message)
        if log.get("Exception", None) is not None:
            log["Exception"] = log["Exception"].split("\n")
            exception_length = len(log["Exception"])
            if exception_length > 15 and not show_all:
                log["Exception"] = log["Exception"][:15]
                lines = str(exception_length - 15)
                hidden_message = lines + " hidden lines (show with --all)"
                log["Exception"].append(hidden_message)

        log["Timestamp"] = datetime.datetime.fromtimestamp(
            int(log.get("Timestamp", 0))
        ).strftime("%I:%M:%S %p %d/%m/%Y")
        logs.append(log)
    message = yaml.safe_dump(logs, default_flow_style=False)
    common.log_output(message, True)


# Get live logs
def get_live_logs(data, level, page_size=5, first_id=0):
    baseurl = common.create_baseurl(data, "/api/v1/logdata/poll")
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    params = {'level': level, 'id': first_id, 'pagesize': page_size}

    r = requests.get(baseurl, headers=headers, cookies=cookies, params=params,
                     verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code == 500:
        message = "Error getting log, "
        message += "database may be locked by backup"
        common.log_output(message, True)
        return
    elif r.status_code != 200:
        common.log_output("Error getting log", True, r.status_code)
        return

    result = r.json()[-page_size:]
    logs = []
    for log in result:
        log["When"] = helper.format_time(log.get("When", ""), True)
        logs.append(log)

    if len(logs) == 0:
        common.log_output("No log entries found", True)
        return

    message = yaml.safe_dump(logs, default_flow_style=False)
    common.log_output(message, True)


# Get stored logs
def get_stored_logs(data, page_size=5, show_all=False):
    baseurl = common.create_baseurl(data, "/api/v1/logdata/log")
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    params = {'pagesize': page_size}

    r = requests.get(baseurl, headers=headers, cookies=cookies, params=params,
                     verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code == 500:
        message = "Error getting log, "
        message += "database may be locked by backup"
        common.log_output(message, True)
        return
    elif r.status_code != 200:
        common.log_output("Error getting log", True, r.status_code)
        return

    result = r.json()[-page_size:]
    logs = []
    for log in result:
        if log.get("Message", None) is not None:
            log["Message"] = log["Message"].split("\n")
            message_length = len(log["Message"])
            if message_length > 15 and not show_all:
                log["Message"] = log["Message"][:15]
                lines = str(message_length - 15)
                hidden_message = lines + " hidden lines (show with --all)"
                log["Message"].append(hidden_message)
        if log.get("Exception", None) is not None:
            log["Exception"] = log["Exception"].split("\n")
            exception_length = len(log["Exception"])
            if exception_length > 15 and not show_all:
                log["Exception"] = log["Exception"][:15]
                lines = str(exception_length - 15)
                hidden_message = lines + " hidden lines (show with --all)"
                log["Exception"].append(hidden_message)
        logs.append(log)

    if len(logs) == 0:
        common.log_output("No log entries found", True)
        return

    message = yaml.safe_dump(logs, default_flow_style=False)
    common.log_output(message, True)


# Repeatedly call other functions until interrupted
def follow_function(function, interval=5):
    try:
        while True:
            compatibility.clear_prompt()
            function()
            timestamp = helper.format_time(datetime.datetime.now(), True)
            common.log_output(timestamp, True)
            common.log_output("Press control+C to quit", True)
            time.sleep(interval)
    except KeyboardInterrupt:
        return


# Call the API to schedule a backup run next
def run_backup(data, backup_id):
    common.verify_token(data)

    path = "/api/v1/backup/" + str(backup_id) + "/run"
    baseurl = common.create_baseurl(data, path)
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    r = requests.post(baseurl, headers=headers, cookies=cookies, verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code != 200:
        common.log_output("Error scheduling backup ", True, r.status_code)
        return
    common.log_output("Backup scheduled", True, 200)


# Call the API to abort a task
def abort_task(data, task_id):
    common.verify_token(data)

    path = "/api/v1/task/" + str(task_id) + "/abort"
    baseurl = common.create_baseurl(data, path)
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    r = requests.post(baseurl, headers=headers, cookies=cookies, verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code != 200:
        common.log_output("Error aborting task ", True, r.status_code)
        return
    common.log_output("Task aborted", True, 200)


# Delete wrapper
def delete_resource(data, resource_type, resource_id,
                    confirm=False, delete_db=False, recreate=False):
    if resource_type == "backup":
        delete_backup(data, resource_id, confirm, delete_db)
    elif resource_type == "database":
        delete_database(data, resource_id, confirm, recreate)
    elif resource_type == "notification":
        delete_notification(data, resource_id)


# Call the API to delete a backup
def delete_backup(data, backup_id, confirm=False, delete_db=False):
    common.verify_token(data)

    # Check if the backup exists
    result = fetch_backups(data, [backup_id], "get")
    if result is None or len(result) == 0:
        return

    if not confirm:
        # Confirm deletion with user
        name = next(iter(result[0]))
        message = 'Delete "' + name + '"? (ID:' + str(backup_id) + ')'
        options = '[y/N]:'
        agree = input(message + ' ' + options)
        if agree not in ["Y", "y", "yes", "YES"]:
            common.log_output("Backup not deleted", True)
            return

    baseurl = common.create_baseurl(data, "/api/v1/backup/" + str(backup_id))
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    # We cannot delete remote files because the captcha is graphical
    payload = {'delete-local-db': delete_db, 'delete-remote-files': False}

    r = requests.delete(baseurl, headers=headers, cookies=cookies,
                        params=payload, verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code != 200:
        common.log_output("Error deleting backup", True, r.status_code)
        return
    common.log_output("Backup deleted", True, 200)


# Call the API to delete a database
def delete_database(data, backup_id, confirm=False, recreate=False):
    common.verify_token(data)

    # Check if the backup exists
    result = fetch_backups(data, [backup_id], "get")
    if result is None or len(result) == 0:
        return

    if not confirm:
        # Confirm deletion with user
        name = next(iter(result[0]))
        message = 'Delete database ' + str(backup_id)
        message += ' belonging to "' + name + '"?'
        options = '[y/N]:'
        agree = input(message + ' ' + options)
        if agree not in ["Y", "y", "yes", "YES"]:
            common.log_output("Database not deleted", True)
            return

    baseurl = common.create_baseurl(data, "/api/v1/backup/" +
                                    str(backup_id) + "/deletedb")
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)

    r = requests.post(baseurl, headers=headers, cookies=cookies,
                      verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code != 200:
        common.log_output("Error deleting database", True, r.status_code)
        return
    common.log_output("Database deleted", True, 200)
    if recreate:
        repair_database(data, backup_id)


# Repair the database
def repair_database(data, backup_id):
    url = "/api/v1/backup/" + backup_id + "/repair"
    fail_message = "Failed to initialize database repair"
    success_message = "Initialized database repair"
    call_backup_subcommand(data, url, fail_message, success_message)


# Verify the remote data files
def verify_remote_files(data, backup_id):
    url = "/api/v1/backup/" + backup_id + "/verify"
    fail_message = "Failed to initialize remote file verification"
    success_message = "Initialized remote file verification"
    call_backup_subcommand(data, url, fail_message, success_message)


# Compact the remote data files
def compact_remote_files(data, backup_id):
    url = "/api/v1/backup/" + backup_id + "/compact"
    fail_message = "Failed to initialize remote data compaction"
    success_message = "Initialized remote file compaction"
    call_backup_subcommand(data, url, fail_message, success_message)


# Method for calling various subcommands for backups
# E.g. "/api/v1/backup/id/compact"
def call_backup_subcommand(data, url, fail_message, success_message):
    common.verify_token(data)

    baseurl = common.create_baseurl(data, url)
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    r = requests.post(baseurl, headers=headers, cookies=cookies,
                      verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code != 200:
        common.log_output(fail_message, True, r.status_code)
        return
    common.log_output(success_message, True, 200)


# Call the API to delete a notification
def delete_notification(data, notification_id):
    common.verify_token(data)

    url = "/api/v1/notification/"
    baseurl = common.create_baseurl(data, url + str(notification_id))
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    r = requests.delete(baseurl, headers=headers, cookies=cookies,
                        verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code == 404:
        common.log_output("Notification not found", True, r.status_code)
        return
    elif r.status_code != 200:
        common.log_output("Error deleting notification", True, r.status_code)
        return
    common.log_output("Notification deleted", True, 200)


def update_backup(data, backup_id, backup_config, import_meta=True):
    common.verify_token(data)

    # Strip metadata if requested
    if import_meta is not None and not import_meta:
        backup_config.get("Backup", {}).pop("Metadata", None)

    baseurl = common.create_baseurl(data, "/api/v1/backup/" + str(backup_id))
    cookies = common.create_cookies(data)
    headers = common.create_headers(data)
    verify = data.get("server", {}).get("verify", True)
    payload = json.dumps(backup_config, default=str)
    r = requests.put(baseurl, headers=headers, cookies=cookies,
                     data=payload, verify=verify)
    common.check_response(data, r.status_code)
    if r.status_code == 404:
        common.log_output("Backup not found", True, r.status_code)
        return
    elif r.status_code != 200:
        common.log_output("Error updating backup", True, r.status_code)
        return
    common.log_output("Backup updated", True, 200)


# Import resource wrapper function
def import_resource(data, resource, import_file, backup_id, import_meta=None):
    if resource == "backup":
        import_backup(data, import_file, backup_id, import_meta)


# Import backup configuration from a YAML or JSON file
def import_backup(data, import_file, backup_id=None, import_meta=None):
    # Don't load nonexisting files
    if os.path.isfile(import_file) is False:
        common.log_output(import_file + " not found", True)
        return

    # Load the import file
    with open(import_file, 'r') as file_handle:
        extension = splitext(import_file)[1]
        if extension.lower() in ['.yml', '.yaml']:
            try:
                backup_config = yaml.safe_load(file_handle)
            except yaml.YAMLError:
                common.log_output("Failed to load file as YAML", True)
                return

        elif extension.lower() == ".json":
            try:
                backup_config = json.load(file_handle)
            except Exception:
                common.log_output("Failed to load file as JSON", True)
                return

    # Determine if we're importing a new backup or updating an existing backup
    if backup_id is not None:
        return update_backup(data, backup_id, backup_config, import_meta)

    common.verify_token(data)

    # Strip metadata if requsted
    if import_meta is None or import_meta is not True:
        backup_config["Backup"]["Metadata"] = {}

    # Prepare the imported JSON object as a string
    backup_config = json.dumps(backup_config, default=str)

    # Upload our JSON string as a file with requests
    files = {
        'config': ('backup_config.json', backup_config, 'application/json')
    }

    # Will eventually support passphrase encrypted configs, but we will
    # need to decrypt them in the client in order to convert them
    payload = {
        'passphrase': '',
        'import_metadata': import_meta,
        'direct': True
    }
    cookies = common.create_cookies(data)
    baseurl = common.create_baseurl(data, "/api/v1/backups/import", True)
    verify = data.get("server", {}).get("verify", True)
    r = requests.post(baseurl, files=files, cookies=cookies, data=payload,
                      verify=verify)
    common.check_response(data, r.status_code)
    # Code for extracting error messages posted with inline javascript
    # and with 200 OK http status code, preventing us from detecting
    # the error otherwise.
    try:
        text = r.text
        start = text.index("if (rp) { rp('")+14
        end = text.index(", line ")
        error = text[start:end].replace("\\'", "'") + "."
        common.log_output(error, True)
        sys.exit(2)
    except ValueError:
        pass
    if r.status_code != 200:
        message = "Error importing backup configuration"
        common.log_output(message, True, r.status_code)
        sys.exit(2)
    common.log_output("Backup job created", True, 200)


# Export resource wrapper function
def export_resource(data, resource, resource_id, output=None,
                    path=None, all_ids=False, timestamp=False):
    if resource == "backup":
        if all_ids:
            # Get all backup configs
            backups = fetch_backup_list(data)
            for backup in backups:
                export_backup(data, backup, output, path, timestamp)
        else:
            # Get backup config
            result = fetch_backups(data, [resource_id], "describe")
            if result is None or len(result) == 0:
                common.log_output("Could not fetch backup", True)
                return
            backup = result[0]
            create_backup_export(data, backup, output, path, timestamp)
    if resource == "serversettings":
        result = fetch_resource_list(data, "serversettings")
        result = list_filter(result, resource)
        create_resource_export(data, result, "serversettings",
                               output, path, timestamp)

# Export backup configuration to either YAML or JSON
def create_backup_export(data, backup, output=None, path=None, timestamp=False):
    # Strip Progress
    backup.pop("Progress", None)

    # Fetch server version
    systeminfo = fetch_resource_list(data, "systeminfo")

    if systeminfo.get("ServerVersion", None) is None:
        common.log_output("Error exporting backup", True)
        sys.exit(2)

    backup["CreatedByVersion"] = systeminfo["ServerVersion"]
    create_resource_export(data, backup, backup['Backup']['Name'], output, path, timestamp)


# Export resource configuration to either YAML or JSON
def create_resource_export(data, resource, name="resource", output=None,
                            path=None, timestamp=False):
    # YAML or JSON?
    if output in ["JSON", "json"]:
        filetype = ".json"
    else:
        filetype = ".yml"

    # Decide on where to output file
    if timestamp:
        stamp = datetime.datetime.now().strftime("%d.%m.%Y_%I.%M_%p")
        file_name = name + "_" + str(stamp) + filetype
    else:
        file_name = name + filetype

    if path is None:
        path = file_name
    else:
        path = common.ensure_trailing_slash(path)
        path = os.path.dirname(expanduser(path)) + "/" + file_name

    # Check if output folder exists
    directory = os.path.dirname(path)
    if directory != '' and not os.path.exists(directory):
        message = "Created directory \"" + directory + "\""
        common.log_output(message, True)
        os.makedirs(directory)
    # Check if output file exists
    if os.path.isfile(path) is True:
        agree = input('File already exists, overwrite? [Y/n]:')
        if agree not in ["Y", "y", "yes", "YES", ""]:
            return
    with open(path, 'w') as file:
        if filetype == ".json":
            file.write(json.dumps(resource, indent=4, default=str))
        else:
            file.write(yaml.dump(resource, default_flow_style=False))
    common.log_output("Created " + path, True, 200)


