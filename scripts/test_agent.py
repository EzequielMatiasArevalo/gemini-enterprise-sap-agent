import os 
import vertexai
import yaml

# AI Engine on Vertex AI 
from vertexai import agent_engines

# Library for AI Engine with ADK
from vertexai.preview import reasoning_engines

# Just to view JSON response formatted
import json
import os
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Test an Agent Engine")
    parser.add_argument("--ae-resource", type=str, required=True, help="The resource name of the Agent Engine")
    return parser.parse_args()

# To load envvars dict from .env file
args = parse_args()
AGENT_ENGINE_RESOURCE=args.ae_resource or os.environ.get("AGENT_ENGINE_RESOURCE")

if not AGENT_ENGINE_RESOURCE:
    print("="*20, " ERROR ", "="*20)

    print("AGENT_ENGINE_RESOURCE is not set. Please set it in the environment variables.")
    print("Available agents:")
    print("-"*20)
    for agent in agent_engines.list():
        print("-"*20)
        print(f"Resource Name: {agent.resource_name}")
        print(f"Display Name: {agent.display_name}")

    print("And set it in the environment variables.")
    print("Run: export AGENT_ENGINE_RESOURCE=<RESOURCE_NAME>")
    print("Run: python scripts/test_agent.py")
    exit(1)

remote_agent = agent_engines.get(AGENT_ENGINE_RESOURCE)

print(f"=================== Remote Agent ============================ \n\
    Name: {remote_agent.display_name}\n\
    Resoruce Name: {remote_agent.resource_name}\n\
    Created/updated at: {remote_agent.update_time} \n\n"
)
# Test the agent
for event in remote_agent.stream_query(
    user_id="user",
    message="Hi, how can you help me?",
):
    print(event)