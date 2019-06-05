"""Mock server to validate requests/responses

"""
from requests import Response
import json
from .base import Base
from .openhltest import Openhltest

class MockServer(object):
    def __init__(self):
        self._mock_storage = {}
        self._mock_storage['openhltest'] = {}

    def _make_NotFoundError(self):
        response = Response()
        response.status_code = 404
        response.reason = 'Not found'
        response.headers['Content-Type'] = 'application/json'
        response._content = r'''{
                "ietf-restconf:errors": {
                    "error": [
                        {
                            "error-type": "application",
                            "error-tag": "general-error",
                            "error-message": "information not found",
                            "error-info": {
                                "info": {
                                    "message": "information not found",
                                    "code": 2003
                                }
                            }
                        }
                    ]
                }
            }'''
        return response

    def _raise_BadRequestError(self):
            response = Response()
            response.status_code = 400
            response.reason = 'unknown-element'
            response.headers['Content-Type'] = 'application/json'
            response._content = r'''{
                    "ietf-restconf:errors": {
                        "error": [
                            {
                                "error-type": "application",
                                "error-tag": "general-error",
                                "error-message": "unknown element",
                                "error-info": {
                                    "info": {
                                        "message": "unknown element",
                                        "code": 2003
                                    }
                                }
                            }
                        ]
                    }
                }'''
            raise  BadRequestError(response)
    
    def _make_python_name(self, yang_name):
        camelCaseName = ''
        for piece in yang_name.split('-'):
            camelCaseName += piece[0].upper() + piece[1:]
        return camelCaseName

    def _remove_restconf_prefix(self, url):
        if url.find('/openhltest:') >= 0:
            url = url[url.find('/openhltest:') + len('/openhltest:'):]
        else:
            if url.find('/restconf/data') > 0:
                url = url[url.find('/restconf/data') + len('/restconf/data'):]
        return url

    def request(self, yang_class, parent, method, url, locals_dict, payload):
        response = Response()
        response.headers['Content-Type'] = 'application/json'
        if method == 'GET':
            url = self._remove_restconf_prefix( url)
            response = self._get_response_from_mock_storage(yang_class, parent, url)
        elif method == 'POST' and url.split('/').pop() in yang_class.YANG_ACTIONS:
            method_name = self._make_python_name(url.split('/').pop())
            if 'Returns:' in getattr(yang_class, method_name).__doc__:
                output = getattr(yang_class, method_name).__doc__.replace('\n', '').replace('\t', '').replace(' ', '')
                start = output.find('Returns:') + len('Returns:')
                output = output[start:output.find('}', start) + 1]
                output = output.replace('string', '')
                response.status_code = 200
                response.reason = 'OK'
                response._content = json.dumps({'openhltest:output': json.loads(output)}, indent=4)
            else:
                response.status_code = 204
                response.reason = 'No Content'
        elif method == 'POST': # POST config message
            url = self._remove_restconf_prefix( url)
            response.status_code = 201
            response.reason = 'Created'
            payload = json.loads(payload)
            key_value = locals_dict[self._make_python_name(yang_class.YANG_KEY)]
            if len(url) > 0:
                response.headers['location'] = 'openhltest:%s/%s=%s' % (url, yang_class.YANG_NAME, key_value)
            else:
                response.headers['location'] = 'openhltest:%s=%s' % ( yang_class.YANG_NAME, key_value)
            self._add_to_mock_storage(yang_class, parent, response.headers['location'], payload)
        elif method == 'PATCH':
            url = self._remove_restconf_prefix( url)
            response.status_code = 204
            response.reason = 'No Content'
            self._update_mock_storage(yang_class, parent, url, payload)
        elif method == 'DELETE':
            url = self._remove_restconf_prefix( url)
            response.status_code = 204
            response.reason = 'No Content'
            self._delete_from_mock_storage(yang_class, parent, url)
        return response

    def _separate_parent_from_url(self, url):
        if url.find('openhltest:') > 0:
            url = url[url.find('openhltest:') + len('openhltest:'):]
        index = url.rfind('/')
        if -1 == index:
            return (None, url)
        else:
            return (url[:index], url[index + 1:])

    def _get_response_from_mock_storage(self, yang_class, parent, url):
        response = Response()
        response.headers['Content-Type'] = 'application/json'
        response.status_code = 200
        response.reason = 'OK'
        category = '%s' % yang_class.YANG_NAME
        content_key = 'openhltest:' + category
        content = {
            content_key: None
        }
        key_value = None
        key_pieces = url.split('/').pop().split('=')
        if len(key_pieces) == 2:
            key_value = url[url.rfind('=') + 1:]
        _, category_storage = self._get_category_storage(yang_class, parent, key_value)
        content[ content_key] = category_storage

        if None == category_storage:
            return self._make_NotFoundError()
        
        response._content = json.dumps(content, indent=4)
        return response

    def _get_category_storage(self, yang_class, parent, key_value = None):
        '''
        Args:
            yang_class: the target node class
            parent: yang_class's parent class instance
            key_value: the target key's value
        Return:
            tuple of (parent storage, target node's storage)
            
        Description:
            For container node: if there'no node created, return {}.
            For list node: 
                if request with key value:
                    if there's no node created: raise exception.
                    else:
                        if the key value is unknown, raise exception.
                        else return the selected list item.
                else:
                    if there's no node created, return [].
                    else return the whole list.
        '''
        category = yang_class.YANG_NAME
        if isinstance(parent, Openhltest):
            parent_storage = self._mock_storage['openhltest']
        else:
            if parent.YANG_KEY == None:
                _, parent_storage = self._get_category_storage(parent, parent._parent)
            else:
                parent_key_name = parent.YANG_KEY[0].upper() + parent.YANG_KEY[1:]
                _, parent_storage = self._get_category_storage(parent, parent._parent, getattr(parent, parent_key_name))
        if None == parent_storage:
            return (None, None)
        if category not in parent_storage:
            if yang_class.YANG_KEYWORD == 'container':
                parent_storage[category] = {}
            elif yang_class.YANG_KEYWORD == 'list':
                if None != key_value:
                    return (parent_storage, None)
                else:
                    parent_storage[category] = []
            return (parent_storage, parent_storage[category])
            
        if None == key_value:
            return (parent_storage, parent_storage[category])
        else:
            item_list = parent_storage[category]
            for item in item_list:
                if item[yang_class.YANG_KEY] == key_value:
                    return (parent_storage, item)
            return (parent_storage, None)

    def _add_to_mock_storage(self, yang_class, parent, url, data):
        """Adds a list item to the mock storage
        yang_class=<class 'openhltest_client.openhltest.sessions.config.ports.ports.Ports'>
        parent=<class 'openhltest_client.openhltest.sessions.config'>
        url=u'openhltest:sessions=s2/config/ports=Ethernet1', 
        data={u'openhltest:ports': [{u'location': u'10.61.65.28/1/1', u'name': u'Ethernet1'}]}
        """
        parent_url, last_url = self._separate_parent_from_url( url)
        key_value = None
        if None != last_url:
            if -1 != last_url.find('='):
                key_value = last_url[last_url.find('=') + 1 :]
        category = '%s' % yang_class.YANG_NAME
        data_category = 'openhltest' + ':' + category
        
        parent_storage, category_storage = self._get_category_storage(yang_class, parent)
        if None == category_storage:
            response = self._make_NotFoundError()
                
        if None != key_value:
            category_storage.append(data[data_category][0])
        else:
            category_storage.update(data[data_category][0])

    def _update_mock_storage(self, yang_class, parent, url, data):
        _, category_storage = self._get_category_storage(yang_class, parent)
        if None == category_storage:
            self._raise_BadRequestError()
        key = None
        if yang_class.YANG_KEYWORD != 'list':
            category_storage.update( json.loads(data))
        else:
            key = url[url.rfind('/'):]
            key = key[key.find('=') + 1:]
            data_index = -1
            for i in range(len(category_storage)):
                if key == category_storage[i][yang_class.YANG_KEY]:
                    data_index = i
                    break
            category_storage[data_index].update(json.loads(data))
        return None

    def _delete_from_mock_storage(self, yang_class, parent, url):
        _, category_storage = self._get_category_storage(yang_class, parent)
        key = None
        if None == category_storage:
            return
        if yang_class.YANG_KEYWORD != 'list':
            category_storage.update( data)
        else:
            key = url[url.rfind('/'):]
            key = key[key.find('=') + 1:]
            data_index = -1
            for i in range(len(category_storage)):
                if key == category_storage[i][yang_class.YANG_KEY]:
                    data_index = i
                    break
            del category_storage[data_index]
