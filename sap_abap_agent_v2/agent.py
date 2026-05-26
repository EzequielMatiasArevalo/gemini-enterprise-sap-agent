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

import os
from google.adk.agents import Agent
from dotenv import load_dotenv
# Import the list of dynamically loaded tools and the prompt
from .tools import get_program, get_class, get_function_group, get_function, get_structure, get_table, get_package, get_type_info, get_include, search_object, get_interface, get_transaction


# Load environment variables from the .env file
load_dotenv()

# --- Agent Definition ---
# This is the main agent. It now has access to multiple tools.
# The model will decide which tool to call based on the user's question
# and the 'description' provided in the tools_config.json for each tool.
root_agent = Agent(
    name="sap_abap_code_agent",
    model="gemini-2.5-flash",
    description="SAP ABAP Code Agent in Google Cloud",
    instruction="""
        'You are an assistant that interacts with SAP ABAP instances via the ADT API. '
        'You can retrieve source code, search for objects, and get information about '
        'ABAP programs, classes, functions, tables, structures, and more. '
        'Use the available tools to help users interact with their SAP systems.'
    """,
    tools=[get_program, get_class, get_function_group, get_function, get_structure, get_table, get_package, get_type_info, get_include, search_object, get_interface, get_transaction],
)