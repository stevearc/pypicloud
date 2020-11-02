""" Simple replacement for distlib SimpleScrapingLocator """
import distlib.locators
import requests
from distlib.locators import SimpleScrapingLocator

from .util import TimedCache


class SimpleJsonLocator(object):

    """ Simple replacement for distlib SimpleScrapingLocator """

    def __init__(self, base_index):
        self.base_index = base_index
        # 16m cache
        self._cache = TimedCache(1000, self._get_releases)

    def get_releases(self, project_name):
        return self._cache[project_name]

    def _get_releases(self, project_name):
        url = "%s/pypi/%s/json" % (self.base_index, project_name)
        response = requests.get(url)
        # Return empty list for 4xx
        if 400 <= response.status_code < 600:
            return []
        response.raise_for_status()
        data = response.json()
        items = []
        summary = data["info"].get("summary")
        for version, releases in data["releases"].items():
            for release in releases:
                try:
                    item = {
                        "name": project_name,
                        "version": version,
                        "summary": summary,
                        "url": release["url"],
                        "digests": release.get("digests", {}),
                        "requires_python": release["requires_python"],
                    }
                except KeyError:
                    continue
                items.append(item)
        return items


class FormattedScrapingLocator(SimpleScrapingLocator):
    def get_releases(self, project_name):
        projects = self.get_project(project_name)
        items = []
        for version, urls in projects["urls"].items():
            for url in urls:
                dist = projects[version]
                digest = projects["digests"].get(url)
                digest_dict = {}
                if digest is not None:
                    digest_dict[digest[0]] = digest[1]
                items.append(
                    {
                        "name": dist.name,
                        "version": dist.version,
                        "summary": dist.metadata.dictionary.get("summary"),
                        "url": url,
                        "digests": digest_dict,
                        "requires_python": dist.metadata.dictionary.get(
                            "requires_python"
                        ),
                    }
                )
        return items


# Distlib checks if wheels are compatible before returning them.
# This is useful if you are attempting to install on the system running
# distlib, but we actually want ALL wheels so we can display them to the
# clients.  So we have to monkey patch the method. I'm sorry.
def is_compatible(wheel, tags=None):
    """ Hacked function to monkey patch into distlib """
    return True


distlib.locators.is_compatible = is_compatible
