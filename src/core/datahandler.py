# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import re

from pymongo import MongoClient
import pymongo.errors
from pymongo import ReadPreference

__document_version__ = "0.1"

class ContactFilter(object):
    def __init__(self, parent = None):
        self.parent = parent
        return

    # re.findall("([^2-90]|\b|^)(\d{3})\W*(\d{3})\W*(\d{4})([^\d]|$)", "157145192411")
    def process(self, message):
        # contact info may be in the email or the url
        phonestr = "1?(\d\s*\d\s*\d)\W*(\d\s*\d\s*\d)\W*(\d\s*\d\s*\d\s*\d)"
        phones = re.findall(phonestr, message.source)
        phones.extend(re.findall(phonestr, message.url))
        emails = re.findall("[\w._-]+\@[\w_-]+\.\w+", message.source)
        emails.extend(re.findall("[\w._-]+\@[\w_-]+\.\w+", message.url))
        today = datetime.datetime.now()
        res = {
                "_id": message.url,
                "v": __document_version__,
                "source": message.source,
                "contact": {
                    # store only unique emails and phones
                    "emails": list(set(emails)),
                    "phones": list(set(["-".join(x) for x in phones]))
                    },
                "dateRange": {
                    "first": today,
                    "last": today,
                }
                }
        if self.parent:
            res = self.parent.process(message)
        contact = {}
        contact["emails"] = emails
        contact["phones"] = phones
        res["contact"] = contact
        return res

class BackPageUrlParser(object):
    def __init__(self, parent = None):
        self.parent = parent
        return

    def process(self, message):
        parsed = re.findall("http://(\w+)\.(\w+)\.com/", message.url)
        today = datetime.datetime.now()
        res = {
                "_id": message.url,
                "v": __document_version__,
                "source": message.source,
                "dateRange": {
                    "first": today,
                    "last": today,
                }
                }
        if self.parent:
            res = self.parent.process(message)
        location = {}
        location["area"] = "" if len(parsed) < 1 else parsed[0][0]
        location["site"] = "" if len(parsed) < 1 else parsed[0][1]
        res["siteInfo"] = location
        return res

class MongoDBDump(object):
    def __init__(self, host, port, dbname, colname,
            processor = ContactFilter(BackPageUrlParser()),
            replset = None, user = None, pwd = None):
        url = "".join([
            "mongodb://",
            host,
            ":",
            port,
            "/"
            ])
        if replset:
            self.conn = MongoClient(url, replicaSet = replset,
                    read_preference = ReadPreference.PRIMARY_PREFERRED)
        else:
            self.conn = MongoClient(url)
        if user and pwd:
            res = self.conn["crawler"].authenticate(user, pwd)
            #TODO: add err handling for else

        self.col = self.conn[dbname][colname]
        self.processor = processor

    def find_by_id(self, _id):
        return self.col.find({"_id": {"$eq": _id}})

    def dump(self, message):
        try:
            curr = self.col.find({"_id": {"$eq": message.url}}).limit(1)
            # document already exists
            if curr.count() > 0:
                # update the last day the page was indexed
                cur = self.col.update_one(
                        { "_id": message.url },
                        { "$set": { "dateRange.last": datetime.datetime.now() } },
                        upsert = True
                        )
            # if we don't already have the website insert the website
            else:
                cur = self.col.insert_one(self.processor.process(message))
        except pymongo.errors.DuplicateKeyError:
            pass
