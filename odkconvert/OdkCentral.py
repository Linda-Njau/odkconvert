#!/bin/python3

# Copyright (c) 2022, 2023 Humanitarian OpenStreetMap Team
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     Odkconvert is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with Odkconvert.  If not, see <https:#www.gnu.org/licenses/>.
#

# The origins of this file was called odk_request.py, and gave me the
# idea to do a much enhanced version. Contributors to the original are:
# Author: hcwinsemius <h.c.winsemius@gmail.com>
# Author: Ivan Gayton <ivangayton@gmail.com>
# Author: Reetta Valimaki <reetta.valimaki8@gmail.com>


import logging
import sys
import os
import requests
from requests.auth import HTTPBasicAuth
import json
import zlib
from datetime import datetime
from base64 import b64encode
import segno
import zlib

# Set log level for urllib
log_level = os.getenv("LOG_LEVEL", default="INFO")
logging.getLogger("urllib3").setLevel(log_level)

log = logging.getLogger(__name__)


class OdkCentral(object):
    def __init__(self, url=None, user=None, passwd=None):
        """A Class for accessing an ODK Central server via it's REST API"""
        if not url:
            url = os.getenv("ODK_CENTRAL_URL", default=None)
        self.url = url
        if not user:
            user = os.getenv("ODK_CENTRAL_USER", default=None)
        self.user = user
        if not passwd:
            passwd = os.getenv("ODK_CENTRAL_PASSWD", default=None)
        self.passwd = passwd
        self.verify=os.getenv("ODK_CENTRAL_SECURE", default=True)
        # These are settings used by ODK Collect
        self.general = {
            "form_update_mode": "match_exactly",
            "autosend": "wifi_and_cellular",
        }
        # If there is a config file with authentication setting, use that
        # so we don't have to supply this all the time. This is only used
        # when odk_client is used, and no parameters are passed in.
        if not self.url:
            home = os.getenv("HOME")
            config = ".odkcentral"
            filespec = home + "/" + config
            if os.path.exists(filespec):
                file = open(filespec, "r")
                for line in file:
                    # Support embedded comments
                    if line[0] == "#":
                        continue
                    # Read the config file for authentication settings
                    tmp = line.split("=")
                    if tmp[0] == "url":
                        self.url = tmp[1].strip("\n")
                    if tmp[0] == "user":
                        self.user = tmp[1].strip("\n")
                    if tmp[0] == "passwd":
                        self.passwd = tmp[1].strip("\n")
            else:
                log.warning("You can put authentication settings in %s" % filespec)
        # Base URL for the REST API
        self.version = "v1"
        self.base = self.url + "/" + self.version + "/"

        # Authentication data
        self.auth = HTTPBasicAuth(self.user, self.passwd)

        # Use a persistant connect, better for multiple requests
        self.session = requests.Session()

        # These are just cached data from the queries
        self.projects = dict()
        self.users = None

    def authenticate(self, url=None, user=None, passwd=None):
        """Setup authenticate to an ODK Central server"""
        if not self.url:
            self.url = url
        if not self.user:
            self.user = user
        if not self.passwd:
            self.passwd = passwd
        # Enable persistent connection, create a cookie for this session
        self.session.headers.update({"accept": "odkcentral"})

        # Connect to the server
        return self.session.get(self.url, auth=self.auth, verify=self.verify)

    def listProjects(self):
        """Fetch a list of projects from an ODK Central server, and
        store it as an indexed list."""
        log.info("Getting a list of projects from %s" % self.url)
        url = f'{self.base}projects'
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        projects = result.json()
        for project in projects:
            if isinstance(project, dict):
                if project.get("id") is not None:
                    self.projects[project['id']] = project
            else:
                log.info("No projects returned. Is this a first run?")
        return projects

    def createProject(self, name=None):
        """Create a new project on an ODK Central server if it doesn't
        already exist"""
        exists = self.findProject(name)
        if exists:
            log.debug(f"Project \"{name}\" already exists.")
            return exists
        else:
            url = f"{self.base}projects"
            result = self.session.post(
                url, auth=self.auth, json={"name": name}, verify=self.verify
            )
            # update the internal list of projects
            self.listProjects()
        return result.json()

    def deleteProject(self, project_id: int):
        """Delete a project on an ODK Central server"""
        url = f"{self.base}projects/{project_id}"
        self.session.delete(url, auth=self.auth, verify=self.verify)
        # update the internal list of projects
        self.listProjects()
        return self.findProject(project_id)

    def findProject(self, project_id=None, name=None):
        """Get the project data from Central"""
        if self.projects:
            if name:
                for key, value in self.projects.items():
                    if name == value["name"]:
                        return value
            if project_id:
                for key, value in self.projects.items():
                    if project_id == value["id"]:
                        return value
        return None

    def findAppUser(self, user_id=None, name=None):
        """Get the data for an app user"""
        if self.appusers:
            if name is not None:
                result = [d for d in self.appusers if d['displayName']==name]
                if result:
                    return result[0]
                else:
                    log.debug(f"No user found with name: {name}")
                    return None
            if user_id is not None:
                result = [d for d in self.appusers if d['id']==user_id]
                if result:
                    return result[0]
                else:
                    log.debug(f"No user found with id: {user_id}")
                    return None
        return None

    def listUsers(self):
        """Fetch a list of users on the ODK Central server"""
        log.info("Getting a list of users from %s" % self.url)
        url = self.base + "users"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        self.users = result.json()
        return self.users

    def dump(self):
        """Dump internal data structures, for debugging purposes only"""
        # print("URL: %s" % self.url)
        # print("User: %s" % self.user)
        # print("Passwd: %s" % self.passwd)
        print("REST URL: %s" % self.base)

        print("There are %d projects on this server" % len(self.projects))
        for id, data in self.projects.items():
            print("\t %s: %s" % (id, data["name"]))
        if self.users:
            print("There are %d users on this server" % len(self.users))
            for data in self.users:
                print("\t %s: %s" % (data["id"], data["email"]))
        else:
            print("There are no users on this server")


class OdkProject(OdkCentral):
    """Class to manipulate a project on an ODK Central server"""

    def __init__(self, url=None, user=None, passwd=None):
        super().__init__(url, user, passwd)
        self.forms = None
        self.submissions = None
        self.data = None
        self.appusers = None
        self.id = None

    def getData(self, keyword):
        return self.data[keyword]

    def listForms(self, id=None):
        """Fetch a list of forms in a project on an ODK Central server."""
        url = f"{self.base}projects/{id}/forms"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        self.forms = result.json()
        return self.forms

    def listAppUsers(self, projectId=None):
        """Fetch a list of app users for a project from an ODK Central server."""
        url = f"{self.base}projects/{projectId}/app-users"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        self.appusers = result.json()
        return self.appusers

    def listAssignments(self, projectId=None):
        """List the Role & Actor assignments for users on a project"""
        url = f"{self.base}projects/{projectId}/assignments"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        return result.json()

    def getDetails(self, projectId=None):
        """Get all the details for a project on an ODK Central server"""
        url = f"{self.base}projects/{projectId}"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        self.data = result.json()
        return self.data

    def dump(self):
        """Dump internal data structures, for debugging purposes only"""
        super().dump()
        if self.forms:
            print("There are %d forms in this project" % len(self.forms))
            for data in self.forms:
                print(
                    "\t %s(%s): %s" % (data["xmlFormId"], data["version"], data["name"])
                )
        if self.data:
            print("Project ID: %s" % self.data["id"])
        print("There are %d submissions in this project" % len(self.submissions))
        for data in self.submissions:
            print("\t%s: %s" % (data["instanceId"], data["createdAt"]))
        print("There are %d app users in this project" % len(self.appusers))
        for data in self.appusers:
            print("\t%s: %s" % (data["id"], data["displayName"]))


class OdkForm(OdkCentral):
    """Class to manipulate a from on an ODK Central server"""

    def __init__(self, url=None, user=None, passwd=None):
        super().__init__(url, user, passwd)
        self.name = None
        # Draft is for a form that isn't published yet
        self.draft = True
        # this is only populated if self.getDetails() is called first.
        self.data = dict()
        self.attach = list()
        self.publish = True
        self.media = list()
        self.xml = None
        self.submissions = list()
        self.appusers = dict()
        # self.xmlFormId = None
        # self.projectId = None

    def getName(self):
        """Extract the name from a form on an ODK Central server"""
        if "name" in self.data:
            return self.data["name"]
        else:
            log.warning("Execute OdkForm.getDetails() to get this data.")

    def getFormId(self):
        """Extract the xmlFormId from a form on an ODK Central server"""
        if "xmlFormId" in self.data:
            return self.data["xmlFormId"]
        else:
            log.warning("Execute OdkForm.getDetails() to get this data.")

    def getDetails(self, projectId=None, xmlFormId=None):
        """Get all the details for a form on an ODK Central server"""
        url = f"{self.base}projects/{projectId}/forms/{xmlFormId}"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        self.data = result.json()
        return result

    def listSubmissions(self, projectId, formId):
        """Fetch a list of submission instances for a given form."""
        url = f"{self.base}projects/{projectId}/forms/{formId}/submissions"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        self.submissions = result.json()
        return self.submissions

    def listAssignments(self, projectId=None, xmlFormId=None):
        """List the Role & Actor assignments for users on a project"""
        url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/assignments"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        return result.json()

    def getSubmission(self, projectId=None, formId=None, disk=False):
        """Fetch a CSV file of the submissions without media to a survey form."""
        url = self.base + f"projects/{projectId}/forms/{formId}/submissions"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        if result.status_code == 200:
            if disk:
                now = datetime.now()
                timestamp = f"{now.year}_{now.hour}_{now.minute}"
                # id = self.forms[0]['xmlFormId']
                filespec = f"/tmp/{formId}_{timestamp}.csv"
                try:
                    file = open(filespec, "xb")
                    file.write(result.content)
                except FileExistsError:
                    file = open(filespec, "wb")
                    file.write(result.content)
                log.info("Wrote CSV file %s" % filespec)
                file.close()
            return result.content
        else:
            log.error(f'Submissions for {projectId}, Form {formId}' + "doesn't exist")
            return None

    def getSubmissionMedia(self, projectId, formId):
        """Fetch a ZIP file of the submissions with media to a survey form."""
        url = self.base + f"projects/{projectId}/forms/{formId}/submissions.csv.zip"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        return result

    def addMedia(self, media=None, filespec=None):
        """Add a data file to this form"""
        # FIXME: this also needs the data
        self.media[filespec] = media

    def addXMLForm(self, projectId=None, xmlFormId=None, xform=None):
        """Add an XML file to this form"""
        self.xml = xform

    def listMedia(self, projectId=None, xmlFormId=None):
        """List all the attchements for this form"""
        if self.draft:
            url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/draft/attachments"
        else:
            url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/attachments"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        self.media = result.json()
        return self.media

    def uploadMedia(self, projectId=None, xmlFormId=None, filespec=None):
        """Upload an attachement to the ODK Central server"""
        title = os.path.basename(os.path.splitext(filespec)[0])
        datafile = f"{title}.geojson"
        xid = xmlFormId.split('_')[2]
        url = f"{self.base}projects/{projectId}/forms/{xid}/draft"
        result = self.session.post(url, auth=self.auth, verify=self.verify)
        if result.status_code == 200:
            log.debug(f"Modified {title} to draft")
        else:
            status = eval(result._content)
            log.error(f"Couldn't modify {title} to draft: {status['message']}")

        url = f"{self.base}projects/{projectId}/forms/{xid}/draft/attachments/{datafile}"
        headers = {"Content-Type": "*/*"}
        file = open(filespec, "rb")
        media = file.read()
        file.close()
        result = self.session.post(
            url, auth=self.auth, data=media, headers=headers, verify=self.verify
        )
        if result.status_code == 200:
            log.debug(f"Uploaded {filespec} to Central")
        else:
            status = eval(result._content)
            log.error(f"Couldn't upload {filespec} to Central: {status['message']}")

        return result

    def getMedia(self, projectId=None, xmlFormId=None, filename=None):
        """Fetch a specific attachment by filename from a submission to a form."""
        if self.draft:
            url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/draft/attachments/{filename}"
        else:
            url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/attachments/{filename}"
        result = self.session.get(url, auth=self.auth, verify=self.verify)
        if result.status_code == 200:
            log.debug(f"fetched {filename} from Central")
        else:
            status = eval(result._content)
            log.error(f"Couldn't fetch {filename} from Central: {status['message']}")
        self.media = result.content
        return self.media

    def createForm(self, projectId=None, xmlFormId=None, filespec=None, draft=None):
        """Create a new form on an ODK Central server"""
        if draft is not None:
            self.draft = draft
        headers = {"Content-Type": "application/xml"}
        if self.draft:
            url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/draft?ignoreWarnings=true&publish=false"
        else:
            url = f"{self.base}projects/{projectId}/forms?ignoreWarnings=true&publish=true"

        # Read the XML or XLS file
        file = open(filespec, "rb")
        xml = file.read()
        file.close()
        log.info("Read %d bytes from %s" % (len(xml), filespec))

        result = self.session.post(url, auth=self.auth,  data=xml, headers=headers, verify=self.verify)
        # epdb.st()
        # FIXME: should update self.forms with the new form
        if result.status_code != 200:
            if result.status_code == 409:
                log.error(f"{xmlFormId} already exists on Central")
            else:
                status = eval(result._content)
                log.error(f"Couldn't create {xmlFormId} on Central: {status['message']}")

        return result.status_code

    def deleteForm(self, projectId=None, xmlFormId=None):
        """Delete a form from an ODK Central server"""
        # FIXME: If your goal is to prevent it from showing up on survey clients like ODK Collect, consider
        # setting its state to closing or closed
        if self.draft:
            url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/draft"
        else:
            url = f"{self.base}projects/{projectId}/forms/{xmlFormId}"
        print(url)
        result = self.session.delete(url, auth=self.auth, verify=self.verify)
        return result

    def publishForm(self, projectId=None, xmlFormId=None):
        """Publish a draft form. When creating a form that isn't a draft, it can get publised then"""
        version = now = datetime.now().strftime("%Y-%m-%dT%TZ")
        xid = xmlFormId.split('_')[2]

        url = f"{self.base}projects/{projectId}/forms/{xid}/draft/publish?version={version}"
        result = self.session.post(url, auth=self.auth, verify=self.verify)
        if result.status_code != 200:
            status = eval(result._content)
            log.error(f"Couldn't publish {xmlFormId} on Central: {status['message']}")
        else:
            log.error(f"Published {xmlFormId} on Central.")
        return result.status_code

    def dump(self):
        """Dump internal data structures, for debugging purposes only"""
        # super().dump()
        entries = len(self.media)
        print("Form has %d attachements" % entries)
        for form in self.media:
            if "name" in form:
                print("Name: %s" % form["name"])


class OdkAppUser(OdkCentral):
    def __init__(self, url=None, user=None, passwd=None):
        """A Class for app user data"""
        super().__init__(url, user, passwd)
        self.user = None
        self.qrcode = None
        self.id = None

    def create(self, projectId=None, name=None):
        """Create a new app-user for a form"""
        url = f"{self.base}projects/{projectId}/app-users"
        result = self.session.post(
            url, auth=self.auth, json={"displayName": name}, verify=self.verify
        )
        self.user = name
        return result

    def delete(self, projectId=None, userId=None):
        """Create a new app-user for a form"""
        url = f"{self.base}projects/{projectId}/app-users/{userId}"
        result = self.session.delete(url, auth=self.auth, verify=self.verify)
        return result

    def updateRole(self, projectId=None, xmlFormId=None, roleId=2, actorId=None):
        """Update the role of an app user for a form"""
        log.info("Update access to XForm %s for %s" % (xmlFormId, actorId))
        url = f"{self.base}projects/{projectId}/forms/{xmlFormId}/assignments/{roleId}/{actorId}"
        result = self.session.post(url, auth=self.auth, verify=self.verify)
        return result

    def grantAccess(
        self, projectId=None, roleId=2, userId=None, xmlFormId=None, actorId=None
    ):
        """Grant access to an app user for a form"""
        url = f"{self.base}projects/{projectId}/forms/{formId}/assignments/{roleId}/{actorId}"
        result = self.session.post(url, auth=self.auth, verify=self.verify)
        return result

    def createQRCode(self, project_id=None, token=None, name=None):
        """Get the QR Code for an app-user"""
        log.info(
            'Generating QR Code for app-user "%s" for project %s' % (name, project_id)
        )
        self.settings = {
            "general": {
                "server_url": f"{self.base}key/{token}/projects/{project_id}",
                "form_update_mode": "manual",
                "basemap_source": "MapBox",
                "autosend": "wifi_and_cellular",
            },
            "project": {"name": f"{name}"},
            "admin": {},
        }
        qr_data = b64encode(zlib.compress(json.dumps(self.settings).encode("utf-8")))
        self.qrcode = segno.make(qr_data, micro=False)
        self.qrcode.save(f"{name}.png", scale=5)
        return qr_data


# This following code is only for debugging purposes, since this is easier
# to use a debugger with instead of pytest.
if __name__ == '__main__':
    logging.basicConfig(
        level=log_level,
        format=(
            "%(asctime)s.%(msecs)03d [%(levelname)s] "
            "%(name)s | %(funcName)s:%(lineno)d | %(message)s"
        ),
        datefmt="%y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Gotta start somewhere...
    project = OdkProject()
    # Start the persistent HTTPS connection to the ODK Central server
    project.authenticate()
    # Get a list of all the projects on this ODK Central server
    project.listProjects()
    # List all the users on this ODK Central server
    project.listUsers()
    # List all the forms for this project. FIXME: don't hardcode the project ID
    project.listForms(4)
    # List all the app users for this project. FIXME: don't hardcode the project ID
    project.listAppUsers(4)
    # List all the submissions for this project. FIXME: don't hardcode the project ID ad form name
    # project.listSubmissions(4, "cemeteries")
    # project.getSubmission(4, "cemeteries")
    # Dump all the internal data
    project.dump()

    # Form management
    form = OdkForm()
    form.authenticate()
    x = form.getDetails(4, "cemeteries")
    # print(x.json())
    # x = form.listMedia(4, "waterpoints", 'uuid:fbe3ef41-6298-40c1-a694-6c9d25a8c476')
    # Make a new form
    # xml = "/home/rob/projects/HOT/odkconvert.git/odkconvert/xlsforms/cemeteries.xml"
    # form.addXMLForm(xml)
    # csv1 = "/home/rob/projects/HOT/odkconvert.git/odkconvert/xlsforms/municipality.csv"
    # csv2 = "/home/rob/projects/HOT/odkconvert.git/odkconvert/xlsforms/towns.csv"
    # form.addMedia(csv1)
    # form.addMedia(csv2)
    x = form.createForm(4, "cemeteries", "cemeteries.xls", True)
    print(x.json())
    # x = form.publish(4, 'cemeteries', "cemeteries.xls")
    print(x.json())
    x = form.uploadMedia(4, "cemeteries", "towns.csv")
    print(x.json())
    x = form.uploadMedia(4, "cemeteries", "municipality.csv")
    print(x.json())
    x = form.listMedia(4, "cemeteries")
    print(x.json())
    form.dump()
