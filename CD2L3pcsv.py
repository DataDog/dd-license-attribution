#!/usr/bin/env python3

import argparse
import http.client
import json
import csv
import sys
import os
import re

def get_owner_repo(repo_url):
    # Regular expression to match GitHub URLs and extract owner and repo
    match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', repo_url)
    if match:
        return match.group(1), match.group(2)
    else:
        raise ValueError("Invalid GitHub URL")

def get_license_info(repo_url):
    # Extract owner and repo using the regular expression
    owner, repo = get_owner_repo(repo_url)
    
    # Make a GET request to the Clearly Defined API to retrieve the repository information
    conn = http.client.HTTPSConnection("api.clearlydefined.io")
    conn.request("GET", f"/definitions?type=git&provider=github&name={repo}&namespace={owner}")
    response = conn.getresponse()
    
    # Check if the request was successful
    if response.status == 200:
        # Extract the license information from the response
        repo_info = json.loads(response.read())
        if len(repo_info.get("data")) > 1:
            latest_release_info = sorted(
                [x for x in repo_info.get("data", []) if x.get("described", {}).get("releaseDate")],
                    key=lambda x: x.get("described", {}).get("releaseDate", "1970-01-01T00:00:00Z"),
                    reverse=True
            )[0]
            # using the latest_release_info coordinates make a new request to get the release information
            coordinates = latest_release_info.get("coordinates");
            r_type = coordinates.get("type")
            r_provider = coordinates.get("provider")
            r_namespace = coordinates.get("namespace")
            r_name = coordinates.get("name")
            r_revision = coordinates.get("revision")
            conn.request("GET", f"/definitions/{r_type}/{r_provider}/{r_namespace}/{r_name}/{r_revision}")
            response = conn.getresponse()
            if response.status == 200:
                # Extract the release information from the response
                repo_info = json.loads(response.read())
                
                # Extract the copyright information
                copyright_info = repo_info.get("licensed").get("facets").get("core").get("attribution").get("parties")
                if copyright_info is None:
                    copyright_info = []
                return {
                    "Component": repo_info.get("described").get("sourceLocation").get("name"), 
                    "Origin": repo_info.get("described").get("urls").get("registry"),
                    "License": repo_info.get("licensed").get("declared"), 
                    "Copyright": " ".join([f'{c}' for c in copyright_info])
                }
            else:
                # print that there is no release information and exit on error
                print("No release information found for revision")
            exit(3)
        else:
            # print that there is no release information and exit on error
            print(f"No release information found for repository {repo}")
            exit(2)
    else:
        # print that there is no release information and exit on error
        print("No repo information found for repository")
        exit(1)


def print_license_info(repo_url):
    # Print the license information to standard output
    writer = csv.writer(sys.stdout)
    # print header
    writer.writerow(["Component", "Origin", "License", "Copyright"])
    # print the license information of the top package
    get_license_info(repo_url)
    # Get the license information of the top package
    license_info = get_license_info(repo_url)
    writer.writerow([license_info["Component"], license_info["Origin"], license_info["License"], license_info["Copyright"]])

    # Get the dependencies information
    dependencies = get_dependencies(repo_url)
    for dependency in dependencies:
        origin = dependency["Origin"]
        if origin == "NOASSERTION" and dependency["Component"].startswith("go:github.com/"):
            origin = "https://" + dependency["Component"].replace("go:", "")
        # Replace git+https: with https:
        origin = origin.replace("git+https:", "https:")
        # Get the license information of the dependency
        license_info = get_license_info(origin)
        writer.writerow([license_info["Component"], license_info["Origin"], license_info["License"], license_info["Copyright"]])        

def get_dependencies(repo_url):
    # Parse the repo_url to extract the owner and repo name
    parts = repo_url.strip('/').split('/')
    owner = parts[-2]
    repo = parts[-1]
    
    # Make a GET request to the GitHub API to retrieve the repository information
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Python http.client"}
    conn = http.client.HTTPSConnection("api.github.com")
    conn.request("GET", f"/repos/{owner}/{repo}/dependency-graph/sbom", headers=headers)
    response = conn.getresponse()

    # Check if the request was successful
    if response.status == 200:
        # Extract the contents of the repository
        repo_sbom = json.loads(response.read())
        dependencies = []
        for package in repo_sbom.get("sbom").get("packages"):
            # Extract the package information
            package_info = {
                "Component": package['name'],
                "Origin": package['downloadLocation'],
            }
            dependencies.append(package_info);
        return dependencies
    else:
        # Print that there is no repository information and exit on error
        print("No repository information found")
        exit(1)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Fetch from Clearly Defined the information about the github project and generate LICENSE-3rdparty.csv file.")
    parser.add_argument("repo_url", help="The URL of the GitHub repository")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Print license information to standard output
    print_license_info(args.repo_url)

if __name__ == "__main__":
    main()