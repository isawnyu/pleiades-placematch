from pprint import pprint
from StringIO import StringIO
import urllib
import urllib2

from plone.app.z3cform.layout import wrap_form
from plone.memoize.instance import memoize
from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from z3c.form import form, field, button
from zope import schema
from zope.interface import Interface, Invalid, invariant

from pleiades.kml.browser import PleiadesBrainPlacemark
from shapely.geometry import asShape
import simplejson
import uuid


class GeoNamesSearch(object):
    """Proxy for GeoNames JSON web service"""
    def link(self, item):
        return 'http://sws.geonames.org/%s/' % item['geonameId']
    def __call__(self, mn, co=None):
        """Returns Python data loaded from GeoNames JSON"""
        # return [{'name': 'Foo'}]
        if not mn:
            return []
        q = dict(name=mn.encode('utf-8'), type='json', featureClass='P')
        if co is not None:
            q.update(country=co)
        u = urllib2.urlopen('http://ws.geonames.org/search', urllib.urlencode(q))
        json = u.read()
        return [dict(n.items() + [('url', self.link(n))]) \
                for n in simplejson.loads(json)['geonames']]
        

class PleiadesSearch(object):
    """Search Pleiades site catalog, returning metadata records"""
    def __call__(self, catalog, mn, an):
        names = [n for n in [mn, an] if n is not None]
        if len(names) == 0:
            return []
        q = u' OR '.join(names)
        return catalog(SearchableText=q, portal_type='Place')


def to_dict(metadata):
    """Convert metadata record to a dict that will be merged with Geonames
    search results"""
    try:
        shape = asShape(metadata.zgeo_geometry)
        bbox = shape.bounds
        centroid = shape.centroid
        center = [centroid.x, centroid.y]
    except ValueError:
        bbox = None
        center = None
    return dict(name=metadata.Title, 
                uid=metadata.UID, 
                id=metadata.getId, 
                placetype=metadata.getFeatureType, 
                url=metadata.getURL(), 
                geometry=metadata.zgeo_geometry, 
                bbox=bbox, 
                center=center
                )


class MatchSet(object):

    def __init__(self, key, mn, co, an, catalog, request):
        self.key = key
        self.mn = mn
        self.co = co
        self.an = an
        self.catalog = catalog
        self.request = request

    def modern_places(self):
        return GeoNamesSearch()(self.mn, self.co)

    def ancient_places(self):
        return [to_dict(r) \
        for r in PleiadesSearch()(self.catalog, self.mn, self.an)]

    def ancient_placemarks(self):
        return [PleiadesBrainPlacemark(r, self.request) \
        for r in PleiadesSearch()(self.catalog, self.mn, self.an)]


class PlaceMatcher(BrowserView):

    kml_template = ViewPageTemplateFile('kml_document.pt')

    def update(self):
        self.key = '0'
        self.mn = self.request.form.get('mn', None)
        self.co = self.request.form.get('co', None)
        self.an = self.request.form.get('an', None)
        self.format =  self.request.form.get('f', '')

    @property
    @memoize
    def alternate_link(self):
        return '%s/@@place-match-form' % self.context.absolute_url()

    def matchsets(self):
        catalog = getToolByName(self.context, 'portal_catalog')
        return [MatchSet(self.key, 
                         self.mn, 
                         self.co, 
                         self.an, 
                         catalog, 
                         self.request
                         )]

    def __call__(self):
        self.update()
        response = self.request.response
        if self.format == 'kml':
            body = self.kml_template().encode('utf-8')
            response.setHeader('Content-Type', 
                'application/vnd.google-earth.kml+xml') 
            response.setHeader('Content-Disposition', 
                               'filename=place-match-%s.kml' % uuid.uuid4())
        else:
            data = [dict(key=s.key, 
                        modern=s.modern_places(), 
                        ancient=s.ancient_places()
                        ) for s in self.matchsets()]
            results = dict(results=[data])
            if self.format == 'json':
                body = simplejson.dumps(results)
                response.setHeader('Content-Type', 'application/json')
            else:
                stream = StringIO()
                pprint(results, stream)
                body = stream.getvalue().encode('utf-8')
                response.setHeader('Content-Type', 'text/plain')
        response.write(body)
        

class IPlaceMatch(Interface):
    """Single place matching interface"""
    mn = schema.TextLine(title=u'Modern name', 
                                 description=u'Modern place name', 
                                 required=True)
    
    co = schema.TextLine(title=u'Country code', 
    description=u'2-letter ISO country code for disambiguation of modern names', 
    required=False)
    
    an = schema.TextLine(title=u'Ancient name', 
        description=u'Transliterated ancient place name', required=False)

    f = schema.Choice(title=u'Results format', 
                      values=('KML', 'JSON', 'Text'), 
                      required=True)


class Form(form.Form):
    fields = field.Fields(IPlaceMatch)
    ignoreContext = True # don't use context to get widget data
    label = u'Search across modern and ancient names for possible matches'

    def update(self):
        super(Form, self).update()
        # Fix widget names
        for key, value in self.widgets.items():
            value.name = key

    @button.buttonAndHandler(u'Apply')
    def handleApply(self, action):
        query = self.request.form.copy()
        query['f'] = query['f'][0].lower()
        self.request.response.redirect(
            '@@place-match?%s' % urllib.urlencode(query))

PlaceMatcherForm = wrap_form(Form)


