
from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView

from pprint import pprint
from StringIO import StringIO
import urllib
import urllib2

from shapely.geometry import asShape
import simplejson


class GeoNamesSearch(object):
    """Proxy for GeoNames JSON web service"""
    def __call__(self, mn, co=None):
        """Returns Python data loaded from GeoNames JSON"""
        if not mn:
            return []
        q = dict(name=mn.encode('utf-8'), type='json', featureClass='P')
        if co is not None:
            q.update(country=co)
        u = urllib2.urlopen('http://ws.geonames.org/search', urllib.urlencode(q))
        json = u.read()
        return simplejson.loads(json)


class PleiadesSearch(object):
    def __call__(self, catalog, mn, an):
        names = [unicode(n, 'utf-8') for n in [mn, an] if n is not None]
        if len(names) == 0:
            return []
        q = u' OR '.join(names)
        metadata = catalog(SearchableText=q, portal_type='Place')
        candidates = []
        for row in metadata:
            try:
                shape = asShape(row.zgeo_geometry)
                bbox = shape.bounds
                centroid = shape.centroid
                center = [centroid.x, centroid.y]
            except ValueError:
                bbox = None
                center = None
            candidates.append(
                dict(name=row.Title, 
                     uid=row.UID, 
                     id=row.getId, 
                     placetype=row.getFeatureType, 
                     url=row.getURL(), 
                     geometry=row.zgeo_geometry, 
                     bbox=bbox, 
                     center=center
                     )
                )
        return candidates


class PlaceMatcher(BrowserView):

    def __call__(self):
        key = self.request.form.get('key')
        mn = self.request.form.get('mn', None)
        co = self.request.form.get('co', None)
        an = self.request.form.get('an', None)
        gn_hits = GeoNamesSearch()(mn, co)
        catalog = getToolByName(self.context, 'portal_catalog')
        pl_hits = PleiadesSearch()(catalog, mn, an)
        stream = StringIO()
        pprint(dict(key=key, modern=gn_hits, ancient=pl_hits), stream)
        return stream.getvalue().encode('utf-8')

