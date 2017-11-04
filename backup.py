#!/usr/bin/python3

import os
import sys
import time
import string
import shlex
from os.path import getsize
import dropbox
from dropbox.files import WriteMode

# Get your app key and secret from the Dropbox developer website
APP_TOKEN = ''
APP_KEY = ''
APP_SECRET = ''
MYSQL_PASS = ''
ARCHIVE_PASS = ''
ARCHIVE_PREFIX = 'vps_backup_'
# The directories that will be backed up fully, without incremental backup
BACKUP_FULL_DIRS = ['/etc']
# The dirs that will be backed up incrementally.
# You can add some other folders i.e.: /var/spool/virtual /home/teamspeak
BACKUP_INC_DIRS = ['/var/www']
# Directories that we do not be backed up. Caches of some sort.
EXCLUDE_DIRS = ['/var/www/.config']
FORCE_FULL_BACKUP = False
CHUNK_SIZE = 20 * 1024 * 1024
# Here will be created a directory 'backup', that will contain all the files to archive
TEMP_DIR = "/root"

# The main backup routine
def main():
  print("Revertron backup 2.0\n")
  # If you have no token
  global APP_TOKEN
  if APP_TOKEN == '':
    authorize()

  curDate = time.strftime("%Y.%m.%d", time.gmtime())
  curDay = time.strftime("%d", time.gmtime())
  backupDelay = time.time() - 86400
  if FORCE_FULL_BACKUP or curDay == "01" or curDay == "15":
    backupDelay = 0
  backupName = ARCHIVE_PREFIX + curDate + '.7z'
  print("Current date:", curDate, "Backup name:", backupName, "\n")

  os.system("mkdir -p " + TEMP_DIR + "/backup")

  # Creating Dropbox object
  dbx = dropbox.Dropbox(APP_TOKEN)

  # Checking connection and auth, uncomment if needed
  print("Linked account data:\n", dbx.users_get_current_account(), "\n")

  print("Deleting old files...")
  os.system("rm -r " + TEMP_DIR + "/backup/*")

  print("Making dump of MySQL databases...")
  os.system("mysqldump --all-databases -uroot -p" + MYSQL_PASS + " -r " + TEMP_DIR + "/backup/backup.sql")

  print("Starting incremental backups...")
  for dir in BACKUP_INC_DIRS:
    sync_dir(dir, backupDelay)

  dirsForBackup = TEMP_DIR + "/backup/*"
  for dir in BACKUP_FULL_DIRS:
    print("Adding for full backup:", dir)
    dirsForBackup = dirsForBackup + " " + dir

  print("All dirs and files for backup are:", dirsForBackup)

  print("Creating archive...")
  os.system("7z a -p" + ARCHIVE_PASS + " " + TEMP_DIR + "/" + backupName + " " + dirsForBackup + " > /dev/null")

  print("Uploading " + backupName + "...")
  upload(dbx, TEMP_DIR + "/" + backupName, "/" + backupName)

  print("Deleting temp files...")
  os.system("rm -r " + TEMP_DIR + "/backup/*")
  os.system("rm " + TEMP_DIR + "/" + backupName);

  print("Backup complete!")

# Gives you the easy way to authorize this cript as Dropbox App
def authorize():
  global APP_TOKEN
  auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(APP_KEY, APP_SECRET)

  authorize_url = auth_flow.start()
  print("1. Go to: " + authorize_url)
  print("2. Click \"Allow\" (you might have to log in first).")
  print("3. Copy the authorization code.\n")
  auth_code = input("Enter the authorization code here: ").strip()

  try:
    oauth_result = auth_flow.finish(auth_code)
  except (Exception, e):
    print('Error: %s' % (e,))
    return

  APP_TOKEN = oauth_result.access_token
  print("\nYour APP_TOKEN:", APP_TOKEN)
  print("Note: don't forget to paste this auth code to the script as APP_TOKEN constant!\n")

# Syncing a directory, copies only files newer then backupDelay
def sync_dir(dir, backupDelay):
  rootdir = dir
  print(" Syncing directory:", rootdir)
  startTime = backupDelay
  for root, subFolders, files in os.walk(rootdir):
    if root in EXCLUDE_DIRS:
      print("  Excluding dir:", root, "with subdirs:", subFolders)
      del subFolders[:]
      continue
    for file in files:
      fname = os.path.join(root, file)
      if os.path.getmtime(fname) > startTime:
        os.system("mkdir -p " + shlex.quote(TEMP_DIR + "/backup" + root))
        fullName = shlex.quote(TEMP_DIR + "/backup" + fname)
        fullCommand = "cp " + shlex.quote(fname) + " " + fullName
        os.system(fullCommand)

# Uploads resulting archive to Dropbox
def upload(dbx, fileName, destPath):
  f = open(fileName,'rb')
  if f:
    fsize = getsize(fileName)
    print("Uploading file of", fsize, "bytes...")
    # if the file is small enough, i.e. < CHUNK_SIZE
    # (Dropbox allows no more than 150MB to use this method)
    if fsize <= CHUNK_SIZE:
      dbx.files_upload(f.read(CHUNK_SIZE), destPath, mode=WriteMode('overwrite'))
      print("File uploaded successfully.")
      f.close()
      return

    upload_session = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
    while f.tell() < fsize:
      cursor = dropbox.files.UploadSessionCursor(session_id=upload_session.session_id, offset=f.tell())
      finish = fsize - f.tell() <= CHUNK_SIZE
      if finish:
        commit = dropbox.files.CommitInfo(path=destPath, autorename=True)
        dbx.files_upload_session_finish(f.read(CHUNK_SIZE), cursor, commit)
      else:
        dbx.files_upload_session_append_v2(f.read(CHUNK_SIZE), cursor)
        cursor.offset = f.tell()
    f.close()
    print("File uploaded successfully.")

# Start the magic!
main()