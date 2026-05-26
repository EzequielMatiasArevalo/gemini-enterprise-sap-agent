# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from dotenv import load_dotenv
import os
import base64
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.auth import HTTPBasicAuth
from typing import Dict, Any
from urllib.parse import quote
import xml.etree.ElementTree as ET
import json


# Load environment variables from the .env file
load_dotenv()

class SapConfig:
    """SAP configuration container."""
    def __init__(self, url: str, username: str, password: str, client: str):
        self.url = url
        self.username = username
        self.password = password
        self.client = client


def get_config() -> SapConfig:
    """
    Retrieves SAP configuration from environment variables.
    
    Returns:
        SapConfig: The SAP configuration object.
    Raises:
        ValueError: If any required environment variable is missing.
    """
    url = os.getenv('SAP_URL')
    username = os.getenv('SAP_USERNAME')
    password = os.getenv('SAP_PASSWORD')
    client = os.getenv('SAP_CLIENT')
    
    if not all([url, username, password, client]):
        raise ValueError(
            "Missing required environment variables. Required variables:\n"
            "- SAP_URL\n"
            "- SAP_USERNAME\n"
            "- SAP_PASSWORD\n"
            "- SAP_CLIENT"
        )
    
    print(url, username, password, client)
    return SapConfig(url, username, password, client)


# Global state for configuration and session
_config: Optional[SapConfig] = None
_csrf_token: Optional[str] = None
_cookies: Optional[str] = None
_session: Optional[requests.Session] = None


def create_session() -> requests.Session:
    """Create a requests session with SSL verification disabled."""
    global _session
    if _session is None:
        _session = requests.Session()
        # Disable SSL verification (equivalent to rejectUnauthorized: false)
        _session.verify = False
        # Disable SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Add retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    
    return _session


def get_base_url() -> str:
    """
    Get the base URL from configuration.
    
    Returns:
        str: The base URL origin.
    Raises:
        ValueError: If URL is invalid.
    """
    global _config
    if not _config:
        _config = get_config()
    
    try:
        url_obj = urlparse(_config.url)
        return f"{url_obj.scheme}://{url_obj.netloc}"
    except Exception as e:
        raise ValueError(f"Invalid URL in configuration: {e}")


def get_auth_headers() -> Dict[str, str]:
    """
    Get authentication headers for SAP requests.
    
    Returns:
        Dict[str, str]: Headers with Authorization and X-SAP-Client.
    """
    global _config
    if not _config:
        _config = get_config()
    
    auth_string = base64.b64encode(
        f"{_config.username}:{_config.password}".encode()
    ).decode()
    
    return {
        'Authorization': f'Basic {auth_string}',
        'X-SAP-Client': _config.client
    }


def fetch_csrf_token(url: str) -> str:
    """
    Fetch CSRF token from SAP system.
    
    Args:
        url: The URL to fetch the token from.
    
    Returns:
        str: The CSRF token.
    Raises:
        Exception: If token cannot be fetched.
    """
    global _cookies
    session = create_session()
    
    try:
        headers = get_auth_headers()
        headers['x-csrf-token'] = 'fetch'
        
        response = session.get(url, headers=headers, timeout=30)
        
        token = response.headers.get('x-csrf-token')
        if not token:
            # Try to get from error response
            if response.status_code >= 400:
                token = response.headers.get('x-csrf-token')
        
        if not token:
            raise ValueError('No CSRF token in response headers')
        
        # Extract and store cookies
        if response.cookies:
            _cookies = '; '.join([f"{c.name}={c.value}" for c in response.cookies])
        elif 'set-cookie' in response.headers:
            # Handle Set-Cookie header (requests handles multiple as a single header)
            cookie_header = response.headers.get('set-cookie', '')
            if cookie_header:
                _cookies = cookie_header
        
        return token
    except requests.exceptions.RequestException as e:
        # Try to get token from error response
        if hasattr(e, 'response') and e.response is not None:
            token = e.response.headers.get('x-csrf-token')
            if token:
                if e.response.cookies:
                    _cookies = '; '.join([f"{c.name}={c.value}" for c in e.response.cookies])
                elif 'set-cookie' in e.response.headers:
                    cookie_header = e.response.headers.get('set-cookie', '')
                    if cookie_header:
                        _cookies = cookie_header
                return token
        raise Exception(f"Failed to fetch CSRF token: {e}")


def make_adt_request(
    url: str,
    method: str = 'GET',
    timeout: int = 30000,
    data: Optional[Any] = None,
    params: Optional[Dict[str, Any]] = None
) -> requests.Response:
    """
    Make an ADT API request to SAP system.
    
    Args:
        url: The full URL for the request.
        method: HTTP method (GET, POST, PUT, etc.).
        timeout: Request timeout in milliseconds (converted to seconds).
        data: Request body data (for POST/PUT).
        params: URL query parameters.
    
    Returns:
        requests.Response: The response object.
    Raises:
        Exception: If request fails.
    """
    global _csrf_token, _cookies
    session = create_session()
    
    # For POST/PUT requests, ensure we have a CSRF token
    if method.upper() in ['POST', 'PUT'] and not _csrf_token:
        _csrf_token = fetch_csrf_token(url)
    
    headers = get_auth_headers()
    
    # Add CSRF token for POST/PUT requests
    if method.upper() in ['POST', 'PUT'] and _csrf_token:
        headers['x-csrf-token'] = _csrf_token
    
    # Add cookies if available
    if _cookies:
        headers['Cookie'] = _cookies
    
    # Convert timeout from milliseconds to seconds
    timeout_seconds = timeout / 1000.0 if timeout > 1000 else timeout
    
    try:
        response = session.request(
            method=method.upper(),
            url=url,
            headers=headers,
            data=data,
            params=params,
            timeout=timeout_seconds
        )
        
        # If we get a 403 with CSRF error, try to fetch a new token and retry
        if (response.status_code == 403 and 
            'CSRF' in str(response.text)):
            _csrf_token = fetch_csrf_token(url)
            headers['x-csrf-token'] = _csrf_token
            response = session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                data=data,
                params=params,
                timeout=timeout_seconds
            )
        
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        raise Exception(f"ADT request failed: {e}")


def return_response(response: requests.Response) -> Dict[str, Any]:
    """
    Format a successful response for ADK tools.
    
    Args:
        response: The requests response object.
    
    Returns:
        Dict with isError=False and content.
    """
    return {
        "isError": False,
        "content": [{
            "type": "text",
            "text": response.text
        }]
    }


def return_error(error: Exception) -> Dict[str, Any]:
    """
    Format an error response for ADK tools.
    
    Args:
        error: The exception that occurred.
    
    Returns:
        Dict with isError=True and error message.
    """
    error_message = str(error)
    if isinstance(error, requests.exceptions.RequestException):
        if hasattr(error, 'response') and error.response is not None:
            error_message = f"HTTP {error.response.status_code}: {error.response.text}"
    
    return {
        "isError": True,
        "content": [{
            "type": "text",
            "text": f"Error: {error_message}"
        }]
    }

#######SAP API Calls###########

def get_program(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP program source code.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'program_name'.
    """
    try:
        if not args.get('program_name'):
            raise ValueError('Program name is required')
        
        encoded_program_name = quote(args['program_name'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/programs/programs/{encoded_program_name}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def get_class(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP class source code.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'class_name'.
    """
    try:
        if not args.get('class_name'):
            raise ValueError('Class name is required')
        
        encoded_class_name = quote(args['class_name'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/oo/classes/{encoded_class_name}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def get_function_group(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP Function Group source code.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'function_group'.
    """
    try:
        if not args.get('function_group'):
            raise ValueError('Function Group is required')
        
        encoded_function_group = quote(args['function_group'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/functions/groups/{encoded_function_group}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def get_function(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP Function Module source code.
    
    Args:
        args (Dict[str, Any]): A dictionary containing 'function_name' and 'function_group'.
    """
    try:
        if not args.get('function_name') or not args.get('function_group'):
            raise ValueError('Function name and group are required')
        
        encoded_function_name = quote(args['function_name'], safe='')
        encoded_function_group = quote(args['function_group'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/functions/groups/{encoded_function_group}/fmodules/{encoded_function_name}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def get_table(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP table structure.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'table_name'.
    """
    try:
        if not args.get('table_name'):
            raise ValueError('Table name is required')
        
        encoded_table_name = quote(args['table_name'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/ddic/tables/{encoded_table_name}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def get_structure(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP Structure.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'structure_name'.
    """
    try:
        if not args.get('structure_name'):
            raise ValueError('Structure name is required')
        
        encoded_structure_name = quote(args['structure_name'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/ddic/structures/{encoded_structure_name}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)

def get_package(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP package details.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'package_name'.
    """
    try:
        if not args.get('package_name'):
            raise ValueError('Package name is required')
        
        node_contents_url = f"{get_base_url()}/sap/bc/adt/repository/nodestructure"
        encoded_package_name = quote(args['package_name'], safe='')
        node_contents_params = {
            'parent_type': 'DEVC/K',
            'parent_name': encoded_package_name,
            'withShortDescriptions': 'true'
        }
        
        response = make_adt_request(
            node_contents_url,
            'POST',
            30000,
            params=node_contents_params
        )
        
        # Parse XML response
        root = ET.fromstring(response.text)
        
        # Extract data from XML (simplified parsing - may need adjustment based on actual XML structure)
        extracted_data = []
        namespace = {'asx': 'http://www.sap.com/abapxml'}
        
        # Find all object nodes
        nodes = root.findall('.//SEU_ADT_REPOSITORY_OBJ_NODE', namespace)
        if not nodes:
            # Try without namespace
            nodes = root.findall('.//SEU_ADT_REPOSITORY_OBJ_NODE')
        
        for node in nodes:
            obj_data = {}
            obj_name = node.find('OBJECT_NAME')
            obj_uri = node.find('OBJECT_URI')
            
            if obj_name is not None and obj_uri is not None:
                obj_data['OBJECT_TYPE'] = node.findtext('OBJECT_TYPE', '')
                obj_data['OBJECT_NAME'] = obj_name.text or ''
                obj_data['OBJECT_DESCRIPTION'] = node.findtext('DESCRIPTION', '')
                obj_data['OBJECT_URI'] = obj_uri.text or ''
                extracted_data.append(obj_data)
        
        return {
            "isError": False,
            "content": [{
                "type": "text",
                "text": json.dumps(extracted_data, indent=2)
            }]
        }
    except Exception as error:
        return return_error(error)


def get_type_info(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP type information.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'type_name'.
    """
    try:
        if not args.get('type_name'):
            raise ValueError('Type name is required')
        
        encoded_type_name = quote(args['type_name'], safe='')
        
        # Try domain first
        try:
            url = f"{get_base_url()}/sap/bc/adt/ddic/domains/{encoded_type_name}/source/main"
            response = make_adt_request(url, 'GET', 30000)
            return return_response(response)
        except Exception:
            # If domain fails, try data element
            try:
                url = f"{get_base_url()}/sap/bc/adt/ddic/dataelements/{encoded_type_name}"
                response = make_adt_request(url, 'GET', 30000)
                return return_response(response)
            except Exception as error:
                return return_error(error)
    except Exception as error:
        return return_error(error)


def get_include(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP Include Source Code.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'include_name'.
    """
    try:
        if not args.get('include_name'):
            raise ValueError('Include name is required')
        
        encoded_include_name = quote(args['include_name'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/programs/includes/{encoded_include_name}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def get_interface(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP interface source code.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'interface_name'.
    """
    try:
        if not args.get('interface_name'):
            raise ValueError('Interface name is required')
        
        encoded_interface_name = quote(args['interface_name'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/oo/interfaces/{encoded_interface_name}/source/main"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def get_transaction(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve ABAP transaction details.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'transaction_name'.
    """
    try:
        if not args.get('transaction_name'):
            raise ValueError('Transaction name is required')
        
        encoded_transaction_name = quote(args['transaction_name'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/repository/informationsystem/objectproperties/values?uri=%2Fsap%2Fbc%2Fadt%2Fvit%2Fwb%2Fobject_type%2Ftrant%2Fobject_name%2F{encoded_transaction_name}&facet=package&facet=appl"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)


def search_object(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for ABAP objects using quick search.
    
    Args:
        args (Dict[str, Any]): A dictionary containing the 'query' and optionally 'maxResults'.
    """
    try:
        if not args.get('query'):
            raise ValueError('Search query is required')
        
        max_results = args.get('maxResults', 100)
        encoded_query = quote(args['query'], safe='')
        url = f"{get_base_url()}/sap/bc/adt/repository/informationsystem/search?operation=quickSearch&query={encoded_query}&maxResults={max_results}"
        
        response = make_adt_request(url, 'GET', 30000)
        return return_response(response)
    except Exception as error:
        return return_error(error)