#!/usr/bin/env python3

import argparse
import http.client
import json
import subprocess
import sys
import os
import re
from pathlib import Path

def request_clearly_define_release_info(package_resource_type, package_resource_provider, package_namespace, package_name, package_revision):
    # Make a GET request to the Clearly Defined API to retrieve the release information
    conn = http.client.HTTPSConnection("api.clearlydefined.io")
    conn.request("GET", f"/definitions/{package_resource_type}/{package_resource_provider}/{package_namespace}/{package_name}/{package_revision}")
    response = conn.getresponse()
    
    # Check if the request was successful
    if response.status == 200:
        # Extract the release information from the response
        release_info = json.loads(response.read())
        return release_info
    else:
        # Print that there is no release information and exit on error
        print("\033[91mNo release information found\033[0m", file=sys.stderr)
        exit(2)

def download_notices_from_clearly_defined(owner, repo, dependencies_notice_dir):
    package_resource_type = "maven"
    package_resource_provider = "github"
    package_revision = "latest"

    # Make a GET request to the Clearly Defined API to retrieve the release information
    release_info = request_clearly_define_release_info(package_resource_type, package_resource_provider, owner, repo, package_revision)

    # Extract the license information from the response
    license = release_info.get("described", {}).get("license")
    if "Apache-2.0" in license:
        print(f"Found APACHE-2.0 license in {owner}/{repo}")
        # pull the NOTICE file into a new owner_repo directory
        os.makedirs(f"{dependencies_notice_dir}/{owner}_{repo}", exist_ok=True)
        os.system(f"wget {release_info.get('described', {}).get('noticeLocation')}")
        if Path(f"NOTICE").exists():
            os.system(f"mv NOTICE {dependencies_notice_dir}/{owner}_{repo}/NOTICE")
    else:
        print(f"License of {owner}/{repo} is not APACHE-2.0", file=sys.stderr)

def download_notices_for_github_project(dependency, dependencies_notice_dir):
    #skip some known dependencies that are not recognized by go-licenses and were
    # manually checked to not have APACHE-2.0 license
    if dependency["Origin"] in ["https://github.com/BurntSushi/toml",
                                "https://github.com/golangci/gofmt", 
                                "https://github.com/goware/modvendor"]:
        print(f"Skipping {dependency['Origin']} as it is known to not have APACHE-2.0 license")
        return
    
    # Extract the owner and repo name
    owner, repo = get_github_owner_repo(dependency["Origin"])
    dep_sanitized = dependency["Origin"].replace("/", "_")

    if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
        print(f"NOTICE file for {owner}/{repo} already downloaded")
        return

    license_paths = [
        f"LICENSE",
        f"LICENSE.md",
        f"License",
        f"License.txt",
        f"LICENSE.txt",
        f"LICENSE.TXT",
        f"LICENSE-APACHE-2.0.txt",
        f"COPYING",
        f"LICENCE",
        f"license",
        f"license.txt",
        f"LICENSE.code",
        f"LICENSE-MIT",
        f"LICENSE.MIT",
        f"license.md",
        f"licence.md", # I know it is misspelled, but it is common in the wild AvaloniaUI/Avalonia for example
        f"LICENCE.md", # I know it is misspelled, but it is common in the wild scalameta/metaconfig for example
        f"LICENSE-2.0.txt",
        f"license/LICENSE.txt",
    ]

    license = None
    branch = "main"

    #special cases where main or master branch is not available
    if dependency["Origin"].endswith(".v1") or dependency["Origin"].endswith("/tree/v1") or dependency["Component"].endswith(".v1"):
        branch = "v1"
        dependency["Origin"] = dependency["Origin"].replace(".v1", "")
        dependency["Origin"] = dependency["Origin"].replace("/tree/v1", "")


    for path in license_paths:
        conn = http.client.HTTPSConnection("raw.githubusercontent.com")
        conn.request("GET", f"/{owner}/{repo}/{branch}/{path}")
        response = conn.getresponse()
        if response.status == 200:
            try:
                license = response.read().decode("utf-8")
            except UnicodeDecodeError:
                license = response.read().decode("windows-1256")
            break

    if "csaf-poc" in dependency["Component"]:
        license = "Apache-2.0" #as declared in README.md
        print(f"Found APACHE-2.0 license in {owner}/{repo}")

    if "License" in dependency:
        license = dependency["License"]

    if license is None:
        # try with branch master
        branch = "master"
        for path in license_paths:
            conn = http.client.HTTPSConnection("raw.githubusercontent.com")
            conn.request("GET", f"/{owner}/{repo}/{branch}/{path}")
            response = conn.getresponse()
            if response.status == 200:
                license = response.read().decode("utf-8")
                break
        if license is None:
            print(f"License of {owner}/{repo} not found", file=sys.stderr)
            exit(1)

    if is_apache_2_license(license):
        print(f"Found APACHE-2.0 license in {owner}/{repo}")
        # pull the NOTICE file into a new owner_repo directory
        os.makedirs(f"{dependencies_notice_dir}/{dep_sanitized}", exist_ok=True)
        os.system(f"wget https://raw.githubusercontent.com/{owner}/{repo}/{branch}/NOTICE")
        if Path(f"NOTICE").exists():
            os.system(f"mv NOTICE {dependencies_notice_dir}/{dep_sanitized}/NOTICE")
    else:
        print(f"License of {owner}/{repo} is not APACHE-2.0", file=sys.stderr)
        for line in license.splitlines():
            if "SPDX" in line:
                print(line, file=sys.stderr)


def download_notices_from_ruby(dependency, dependencies_notice_dir):
    # Skip some known dependencies that are not recognized by gem and were
    # manually checked to not have APACHE-2.0 license
    if dependency["Origin"] in ["webrick", "hawk-auth"]:
        print(f"Skipping {dependency['Origin']} as it is known to not have APACHE-2.0 license")
        return
    
    license = None
    # Get the package metadata using gem show
    license_result = subprocess.run(f"gem spec {dependency['Origin']} license", shell=True, capture_output=True, text=True)
    if license_result.returncode == 0:
        license = license_result.stdout.strip().replace("--- ", "").replace("\n", "")
        homepage_result = subprocess.run(f"gem spec {dependency['Origin']} homepage", shell=True, capture_output=True, text=True)
        if homepage_result.returncode != 0:
            print(f"Failed to get metadata for {dependency['Origin']}", file=sys.stderr)
            exit(1)
        dependency["Origin"] = homepage_result.stdout.strip().replace("--- ", "").replace("\n", "")

    if license is None:
        #make http_request to the rubygems api to get the license
        conn = http.client.HTTPSConnection("rubygems.org")
        conn.request("GET", f"/api/v1/gems/{dependency['Origin']}.json")
        response = conn.getresponse()
        if response.status == 200:
            package_info = json.loads(response.read())
            license = package_info.get("licenses")
            dependency["Origin"] = package_info.get("source_code_uri")
            if dependency["Origin"] is None:
                dependency["Origin"] = package_info.get("homepage_uri")
            #if the array license is empty
            if not license: #delegating to github/gitlab resolution
                if "github.com" in dependency["Origin"]:
                    download_notices_for_github_project(dependency, dependencies_notice_dir)
                    return
                elif "gitlab.com" in dependency["Origin"]:
                    download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
                    return
                else:
                    print(f"Unknown repository URL: {dependency['Origin']}", file=sys.stderr)
                    exit(1)
        else:
            print(f"Failed to get metadata for {dependency['Origin']}", file=sys.stderr)
            exit(1)
        if license is None:
            print(f"License information not found for {dependency['Origin']}", file=sys.stderr)
            exit(1)

    if is_apache_2_license(license):
        print(f"Found APACHE-2.0 license in {dependency['Origin']}")
        # Extract the owner and repo name
        owner, repo = get_github_owner_repo(dependency["Origin"])
        dep_sanitized = dependency["Origin"].replace("/", "_")
        # Check if the NOTICE file already exists
        if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
            print(f"NOTICE file for {owner}/{repo} already downloaded")
            return
        # Download the NOTICE file from the repository
        if "github.com" in dependency["Origin"]:
            download_notices_for_github_project(dependency, dependencies_notice_dir)
        elif "gitlab.com" in dependency["Origin"]:
            download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
        else:
            print(f"Unknown repository URL: {dependency['Origin']}", file=sys.stderr)
            exit(1)
    else:
        if "---" in dependency["Origin"]:
            pass
        print(f"License of {dependency['Origin']} is not APACHE-2.0", file=sys.stderr)


def download_notices_from_pip(dependency, dependencies_notice_dir):
    #special cases with native preinstalled dependencies that are not APACHE-2.0 licensed
    if dependency["Origin"] in ["mariadb", "pylibmc", "django-pylibmc", "mysqlclient", "pysqlite3", "pysqlite3-binary"]:
        print(f"Skipping {dependency['Origin']} as it is known to not have APACHE-2.0 license")
        return
    
    #special cases that need a redirect to the correct repository
    if dependency["Origin"] in ["backports-zoneinfo"]:
        dependency["Origin"] = "https://github.com/pganssle/zoneinfo"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency["Origin"] in ["requests"]:
        dependency["Origin"] = "https://github.com/psf/requests"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency["Origin"] in ["libvirt-python"]:
        dependency["Origin"] = "https://gitlab.com/libvirt/libvirt"
        download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
        return
    if dependency["Origin"] in ["cryptography"]:
        dependency["Origin"] = "https://github.com/pyca/cryptography"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    if dependency["Origin"] in ["datadog-checks-dependency-provider"]:
        dependency["Origin"] = "https://github.com/DataDog/integrations-core"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:sniffio"]:
        dependency["Origin"] = "https://github.com/python-trio/sniffio"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:aiofiles"]:
        dependency["Origin"] = "https://github.com/Tinche/aiofiles"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    if dependency["Component"] in ["pip:tornado"]:
        dependency["Origin"] = "https://github.com/tornadoweb/tornado"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"].startswith("pip:pinecone-"):
        dependency["Origin"] = "https://github.com/pinecone-io/pinecone-python-client"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:pyopenssl"]:
        dependency["Origin"] = "https://github.com/pyca/pyopenssl"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:snowflake-connector-python"]:
        dependency["Origin"] = "https://github.com/snowflakedb/snowflake-connector-python"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:rsa"]:
        dependency["Origin"] = "https://github.com/sybrenstuvel/python-rsa"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:immutables"]:
        dependency["Origin"] = "https://github.com/MagicStack/immutables"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:asyncpg"]:
        dependency["Origin"] = "https://github.com/MagicStack/asyncpg"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    if dependency["Component"] in ["pip:geomet"]:
        dependency["Origin"] = "https://github.com/geomet/geomet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"].startswith("pip:opentelemetry-"):
        dependency["Origin"] = "https://github.com/open-telemetry/opentelemetry-python"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:uritemplate"]:
        dependency["Origin"] = "https://github.com/python-hyper/uritemplate"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] in ["pip:pony"]:
        dependency["Origin"] = "https://github.com/ponyorm/pony"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return


    package_name = dependency["Origin"]
    dep_sanitized = package_name.replace("/", "_")
    #skip if NOTICE was already downloaded
    if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
        print(f"NOTICE file for {package_name} already downloaded")
        return

    # Check if the NOTICE file already exists
    if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
        print(f"NOTICE file for {package_name} already downloaded")
        return

    if "License" in dependency and dependency["License"] is not None and not is_apache_2_license(dependency["License"]):
        print(f"License of {package_name} is not APACHE-2.0", file=sys.stderr)
        return
    
    if dependency["Component"] == "pip:gearman":
        dependency["Origin"] = "https://github.com/Yelp/python-gearman"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Component"] == "pip:ibm-db":
        dependency["Origin"] = "https://github.com/ibmdb/python-ibmdb"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    # Get the package metadata using pip show
    # Activate the virtual environment and install the package to get the metadata
    result = subprocess.run("source venv/bin/activate && pip3 install " + package_name, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        # append the following line to the failed_to_install_py_packages.txt file
        with open("failed_to_install_py_packages.txt", "a") as f:
            f.write(f"{package_name} : {dependency['Component']} \n")
        print(f"Failed to install {package_name}", file=sys.stderr)
        exit(1)
    
    result = subprocess.run("source venv/bin/activate && pip3 show " + package_name, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        # append the following line to the failed_to_install_py_packages.txt file
        with open("failed_to_get_md_py_packages.txt", "a") as f:
            f.write(f"{package_name} : {dependency['Component']} \n")
        print(f"Failed to get metadata for {package_name}", file=sys.stderr)
        exit(1)

    # Extract the license information from the metadata
    license = None
    for line in result.stdout.splitlines():
        if line.startswith("License:"):
            license = line.split(":", 1)[1].strip()
            break

    if license is None:
        print(f"License information not found for {package_name}", file=sys.stderr)
        exit(1)

    # Check if the license is Apache-2.0
    if is_apache_2_license(license):
        print(f"Found APACHE-2.0 license in {package_name}")
        #extract info from metadata
        location = None
        version = None
        home_page = None

        for line in result.stdout.splitlines():
            if line.startswith("Location:"):
                location = line.split(":", 1)[1].strip()
            if line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
            if line.startswith("Home-page:"):
                home_page = line.split(":", 1)[1].strip()

        if location is not None and version is not None:
            notice_location = location + package_name + version + ".dist-info/NOTICE"
            if Path(notice_location).exists():    
                os.makedirs(f"{dependencies_notice_dir}/{dep_sanitized}", exist_ok=True)
                # copy the notice file to the dependencies directory
                os.system(f"cp {notice_location} {dependencies_notice_dir}/{dep_sanitized}/NOTICE")
                return

        #when location doesn't get it, extract Home-page from the metadata and try to download
        if home_page is not None:
            # github repositories have the NOTICE file in the root
            dependency["Origin"] = home_page
            if "github.com" in home_page:
                download_notices_for_github_project(dependency, dependencies_notice_dir)
            elif "gitlab.com" in home_page:
                download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
            else:
                print(f"Unknown repository URL: {home_page}", file=sys.stderr)
                exit(1)
        else:
            print(f"Unknown repository URL: {home_page}", file=sys.stderr)
            exit(1)
    else:
        print(f"License of {package_name} is not APACHE-2.0", file=sys.stderr)
        for line in license.splitlines():
            if "SPDX" in line:
                print(line, file=sys.stderr)


def download_notices_from_cargo(dependency, dependencies_notice_dir, cargo_deps_licenses):
    if dependency["Origin"] in ["fuchsia-cprng", "bollard-stubs"]:
        print(f"Skipping {dependency['Origin']} as it was manually reviewed")
        return
    if dependency["Component"] in ["rust:datadog-ddsketch"]:
        dependency["Origin"] = "https://github.com/DataDog/libdatadog"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    #read the license json generated by cargo and check if the license is APACHE-2.0
    package_info = None
    with open(cargo_deps_licenses) as f:
        packages_info = json.load(f)   
    for package in packages_info:
        if package["name"] == dependency["Origin"]:
            package_info = package
            break

    license = dependency.get("License")
    if license is None:
        license = package_info.get("license")
    if  license is None or is_apache_2_license(license):
        print(f"Found APACHE-2.0 license in {dependency['Origin']}")
        # correcting imcomplete data from CARGO
        if dependency["Component"] == "rust:cpu-time":
            repo_url = "https://github.com/tailhook/cpu-time"
        elif dependency["Component"] == "rust:sync_wrapper":
            repo_url = "https://github.com/Actyx/sync_wrapper"
        elif dependency["Component"] == "rust:hyper-timeout":
            repo_url = "https://github.com/hjr3/hyper-timeout"
        elif dependency["Component"] == "rust:multimap":
            repo_url = "https://github.com/havarnov/multimap"
        elif dependency["Component"] == "rust:tokio-io-timeout":
            repo_url = "https://github.com/sfackler/tokio-io-timeout"
        elif dependency["Component"] == "rust:prost-build":
            repo_url = "https://github.com/tokio-rs/prost"
        elif dependency["Component"] == "rust:prost-types":
            repo_url = "https://github.com/tokio-rs/prost"
        elif dependency["Component"] == "rust:serde_regex":
            repo_url = "https://github.com/tailhook/serde-regex"
        elif dependency["Component"] == "rust:glibc_version":
            repo_url = "https://github.com/delta-io/delta-rs"
        elif dependency["Component"] == "rust:hdrhistogram":
            repo_url = "https://github.com/HdrHistogram/HdrHistogram_rust"
        elif dependency["Component"] == "rust:datadog-alloc":
            repo_url = "https://github.com/DataDog/libdatadog"
        elif dependency["Component"] == "rust:datadog-profiling":
            repo_url = "https://github.com/DataDog/ddprof"
        elif dependency["Component"] == "rust:ddcommon":
            repo_url = "https://github.com/DataDog/libdatadog"
        elif dependency["Component"] == "rust:sha1":
            repo_url = "https://github.com/RustCrypto/hashes"
        elif dependency["Component"] == "rust:ct-logs":
            repo_url = "https://github.com/ctz/ct-logs"
        else:
            repo_url = package_info["repository"]
        
        # Download the NOTICE file from the repository
        dependency["Origin"] = repo_url
        if "github.com" in repo_url:
            # Extract the owner and repo name
            owner, repo = get_github_owner_repo(repo_url)
            dep_sanitized = dependency["Origin"].replace("/", "_")
            # Check if the NOTICE file already exists
            if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
                print(f"NOTICE file for {owner}/{repo} already downloaded")
                return
            #get Cargo.toml file to check license
            conn = http.client.HTTPSConnection("raw.githubusercontent.com")
            conn.request("GET", f"/{owner}/{repo}/main/Cargo.toml")
            response = conn.getresponse()
            if response.status == 200:
                response = response.read().decode("utf-8")
                match = re.search(r'license = "([^"]+)"', response)
                if match:
                    dependency['License']  = match.group(1)            
            else:
                conn = http.client.HTTPSConnection("raw.githubusercontent.com")
                conn.request("GET", f"/{owner}/{repo}/master/Cargo.toml")
                response = conn.getresponse()
                if response.status == 200:
                    response = response.read().decode("utf-8")
                    match = re.search(r'license = "([^"]+)"', response)
                    if match:
                        dependency['License']  = match.group(1)            
            download_notices_for_github_project(dependency, dependencies_notice_dir)
        elif "gitlab.com" in repo_url:
                        # Extract the owner and repo name
            owner, repo = get_gitlab_owner_repo(repo_url)
            dep_sanitized = dependency["Origin"].replace("/", "_")
            # Check if the NOTICE file already exists
            if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
                print(f"NOTICE file for {owner}/{repo} already downloaded")
                return
            download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
        else:
            print(f"Unknown repository URL: {repo_url}", file=sys.stderr)
            exit(1)
    else:
        print(f"License of {dependency['Origin']} is not APACHE-2.0", file=sys.stderr)

def download_notices_for_gitlab_project(dependency, dependencies_notice_dir):
    owner, repo = get_gitlab_owner_repo(dependency["Origin"])
    dep_sanitized = dependency["Origin"].replace("/", "_")

    if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
        print(f"NOTICE file for {owner}/{repo} already downloaded")
        return

    license_paths = [
        f"LICENSE",
        f"LICENSE.md",
        f"License",
        f"License.txt",
        f"LICENSE.txt",
        f"LICENSE-APACHE-2.0.txt",
        f"COPYING",
        f"LICENCE",
        f"license",
        f"LICENSE.code",
    ]

    license = None
    # Special cases reviewed by hand because info is not easily retrievable
    if dependency["Origin"] == "https://gitlab.com/CreepySkeleton/proc-macro-error":
        license = "Apache-2.0"
        branch = "master"

    if license is None:
        branch = "main"
        for path in license_paths:
            conn = http.client.HTTPSConnection("gitlab.com")
            conn.request("GET", f"/{owner}/{repo}/-/raw/{branch}/{path}")
            response = conn.getresponse()
            if response.status == 200:
                license = response.read().decode("utf-8")
                break

    if license is None:
        # try with branch master
        branch = "master"
        for path in license_paths:
            conn = http.client.HTTPSConnection("gitlab.com")
            conn.request("GET", f"/{owner}/{repo}/-/raw/{branch}/{path}")
            response = conn.getresponse()
            if response.status == 200:
                license = response.read().decode("utf-8")
                break
        if license is None:
            print(f"License of {owner}/{repo} not found", file=sys.stderr)
            exit(1)

    if is_apache_2_license(license):
        print(f"Found APACHE-2.0 license in {owner}/{repo}")
        # pull the NOTICE file into a new owner_repo directory
        os.makedirs(f"{dependencies_notice_dir}/{dep_sanitized}", exist_ok=True)
        os.system(f"wget https://gitlab.com/{owner}/{repo}/-/raw/{branch}/NOTICE")
        if Path(f"NOTICE").exists():
            os.system(f"mv NOTICE {dependencies_notice_dir}/{dep_sanitized}/NOTICE")
        else:
            os.system(f"wget https://gitlab.com/{owner}/{repo}/-/raw/{branch}/NOTICE.txt")
            if Path(f"NOTICE.txt").exists():
                os.system(f"mv NOTICE.txt {dependencies_notice_dir}/{dep_sanitized}/NOTICE")
    else:
        print(f"License of {owner}/{repo} is not APACHE-2.0", file=sys.stderr)
        for line in license.splitlines():
            if "SPDX" in line:
                print(line, file=sys.stderr)

def download_notices_from_npm(dependency, dependencies_notice_dir):
    # Special cases
    if dependency["Origin"] in ["@datadog/sma"]:
        print(f"Skipping {dependency['Origin']} as needs further research")
        return
    # Known dependencies that are not recognized by npm but manually checked not APACHE-2.0
    if dependency["Component"] in ["npm:@airbnb/node-memwatch"]:
        print(f"Skipping {dependency['Origin']} as it is known to not have APACHE-2.0 license")
        return

    # Known dependencies that are hosted in non standard locations but manually checked 
    if dependency["Origin"] in ["atob", "btoa"]:
        print(f"Skipping {dependency['Origin']}")
        return

    # Get the package metadata using npm show
    result = subprocess.run(f"npm show {dependency['Origin']} --json", shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to get metadata for {dependency['Origin']}", file=sys.stderr)
        exit(1)

    # Extract the license information from the metadata
    package_info = json.loads(result.stdout)
    license = package_info.get("license")
    if not license or is_apache_2_license(license):
        repo_url = json.loads(result.stdout)["repository"]["url"]
        # Extract the owner and repo name
        owner, repo = get_github_owner_repo(repo_url)
        dep_sanitized = dependency["Origin"].replace("/", "_")
        # Check if the NOTICE file already exists
        if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
            print(f"NOTICE file for {owner}/{repo} already downloaded")
            return

        # Download the NOTICE file from the repository
        dependency["Origin"] = repo_url
        if "github.com" in repo_url:
            download_notices_for_github_project(dependency, dependencies_notice_dir)
        elif "gitlab.com" in repo_url:
            download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
        else:
            print(f"Unknown repository URL: {repo_url}", file=sys.stderr)
            exit(1)
    else:
        print(f"License of {dependency['Origin']} is not APACHE-2.0", file=sys.stderr)


def download_notices_for_gopkg_project(dependency, base_repo_dir, dependencies_notice_dir, temp_debug_dir):
    if "BurntSushi" in dependency["Origin"]:
        print("Found toml package")
    
    #skip some known dependencies that are not recognized by go-licenses and were
    # manually checked to not have APACHE-2.0 license
    if dependency["Origin"] in ["golang.org/x/arch", 
                                "golang.org/x/time",
                                "golang.org/x/net",
                                "golang.org/x/text",
                                "golang.org/x/mobile",
                                "golang.org/x/exp",
                                "golang.org/x/sys",
                                "golang.org/x/crypto", 
                                "modernc.org/ccgo/v3", 
                                "golang.org/x/sync",
                                "golang.org/x/perf",
                                "golang.org/x/tools",
                                "golang.org/x/mod", 
                                "inet.af/netaddr", 
                                "BurntSushi/toml", 
                                "golangci/gofmt",]:
        print(f"Skipping {dependency['Origin']} as it is known to not have APACHE-2.0 license")
        return
    
    if dependency["Origin"] == "gopkg.in/DataDog/dd-trace-go.v1":
        dependency["Origin"] = "https://github.com/DataDog/dd-trace-go"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    if dependency["Origin"] == "gopkg.in/check.v1":
        dependency["Origin"] = "https://github.com/go-check/check"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    #replacing dependency origin on some cases that go-licenses hang up the process
    if dependency["Origin"] == "go.mongodb.org/mongo-driver":
        dependency["Origin"] = "https://github.com/mongodb/mongo-go-driver"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    if dependency["Origin"].startswith("sigs.k8s.io"):
        repo = dependency["Origin"].split("/")[1]
        dependency["Origin"] = f"https://github.com/kubernetes-sigs/{repo}"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Origin"].startswith("go.etcd.io/etcd"):
        dependency["Origin"] = "https://github.com/etcd-io/etcd"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Origin"] == "honnef.co/go/tools":
        dependency["Origin"] = "https://github.com/dominikh/go-tools"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return

    #Hot fix for all the kubernetes dependencies that are returning errors because they were relocated wihtout the 3xx 
    if dependency["Origin"].startswith("k8s.io"):
        repo = dependency["Origin"].split("/")[1]
        dependency["Origin"] = f"https://github.com/kubernetes/{repo}"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if "/neurosnap/sentences" in dependency["Origin"]:
        dependency["Origin"] = "https://github.com/neurosnap/sentences"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    if dependency["Origin"].endswith("go.opentelemetry.io/collector/pdata/testdata"):
        #remove testdata from the url its an error in the declaration-
        dependency["Origin"] = dependency["Origin"].replace("/testdata", "")
    
    #sanitized dependency name
    dep_sanitized = dependency["Origin"].replace("/", "_")
    # access the local repository
    cwd = os.getcwd()
    os.chdir(base_repo_dir)
    # go-licenses to check what licenses are used by the package
    license_data = os.popen(f"go-licenses csv {dependency['Origin']}").read()
    os.chdir(cwd) # return to the original directory
    if license_data == "":
        # replace origin with the correct url for go-licenses
        #Origin of google.golang.org/genproto/googleapis/rpc is actually github.com/googleapis/go-genproto
        # if url starts with google.golang.org access the url and scrap the repository url from the passed url website
        #first split the url by / to get the domain
        if dependency["Origin"].startswith("https://"):
            dependency["Origin"] = dependency["Origin"].replace("https://", "")
        domain = dependency["Origin"].split("/")[0]
        path = dependency["Origin"].replace(domain, "")
        if "gitlab.com" in dependency["Origin"]:
            download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
            return
        if "github.com" in dependency["Origin"]:
            download_notices_for_github_project(dependency, dependencies_notice_dir)
            return
        conn = http.client.HTTPSConnection(domain)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            while response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if location.startswith('/'):
                    conn = http.client.HTTPSConnection(domain)
                    path = location
                else:
                    match = re.match(r'https?://([^/]+)(/.*)', location)
                    if match:
                        domain, path = match.groups()
                        conn = http.client.HTTPSConnection(domain)
                conn.request("GET", path)
                response = conn.getresponse()
            if response.status == 200:
                repo_info = response.read().decode("utf-8")
                # if there is an html redirect use it to get the repository url
                if "http-equiv=\"refresh\"" in repo_info:
                    # an example to match would be: <meta http-equiv="refresh" content="0; url=https://pkg.go.dev/go-simpler.org/musttag"
                    match = re.search(r'<meta http-equiv="refresh" content="0; url=(https://[^"]+)"', repo_info)
                    if match:
                        domain, path = match.group(1).split("/", 3)[2:]
                        conn = http.client.HTTPSConnection(domain)
                        conn.request("GET", f"/{path}")
                        response = conn.getresponse()
                        if response.status == 200:
                            repo_info = response.read().decode("utf-8")
                        while response.status in (301, 302, 303, 307, 308):
                            location = response.getheader('Location')
                            if location.startswith('/'):
                                conn = http.client.HTTPSConnection(domain)
                                path = location
                            else:
                                match = re.match(r'https?://([^/]+)(/.*)', location)
                                if match:
                                    domain, path = match.groups()
                                    conn = http.client.HTTPSConnection(domain)
                            conn.request("GET", path)
                            response = conn.getresponse()
                            repo_info = response.read().decode("utf-8")
                # search for the repository url, it is in a <a> tag inside a div class UnitMeta-repo
                # here is an example of the html structure to match
                # <div class="UnitMeta-repo">\n      \n        <a href="https://github.com/googleapis/go-genproto" title="https://github.com/googleapis/go-genproto" target="_blank" rel="noopener">\n          github.com/googleapis/go-genproto\n        </a>
                match = re.search(r'<div class="UnitMeta-repo">\s*<a href="([^"]+)"', repo_info)
                if match:
                    dependency["Origin"] = match.group(1)
                    if "gitlab.com" in dependency["Origin"]:
                        download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
                        return
                    if "github.com" in dependency["Origin"]:
                        download_notices_for_github_project(dependency, dependencies_notice_dir)
                        return
                else:
                    # Here is another example to match <meta name="go-import" content="cloud.google.com/go git https://github.com/googleapis/google-cloud-go">
                    match = re.search(r'<meta name="go-import" content="[^ ]+ git (http.+)">', repo_info)
                    if match:
                        dependency["Origin"] = match.group(1)
                        if "github.com" in dependency["Origin"]:
                            download_notices_for_github_project(dependency, dependencies_notice_dir)
                            return
                # example of gopkg repository source element
                # <a class="btn btn-lg btn-info" href="https://github.com/go-tomb/tomb/tree/v1"><i class="fa fa-github"></i> Source Code</a>
                if "gopkg.in" in dependency["Origin"]:
                    # Match only the URL for the "Source Code" button, allowing for additional HTML tags inside
                    match = re.search(r'<a class="btn btn-lg btn-info" href="([^"]+)"[^>]*>.*?Source Code.*?</a>', repo_info, re.DOTALL)
                    if match:
                        dependency["Origin"] = match.group(1)
                        if "gitlab.com" in dependency["Origin"]:
                            download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
                            return
                        if "github.com" in dependency["Origin"]:
                            download_notices_for_github_project(dependency, dependencies_notice_dir)
                            return
            else:
                # try to get the respository url from the Origin first part hoping a redirect to github
                domain = dependency["Origin"].split("/")[0]
                conn = http.client.HTTPSConnection(domain)
                base_path = dependency["Origin"].split("/")[1]
                conn.request("GET", f"/{base_path}")
                response = conn.getresponse()
                while response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if location.startswith('/'):
                        conn = http.client.HTTPSConnection(domain)
                        path = location
                    else:
                        match = re.match(r'https?://([^/]+)(/.*)', location)
                        if match:
                            domain, path = match.groups()
                            conn = http.client.HTTPSConnection(domain)
                    conn.request("GET", path)
                    response = conn.getresponse()
                if domain == "github.com" and response.status == 200:
                    dependency["Origin"] = f"https://{domain}{path}"
                    download_notices_for_github_project(dependency, dependencies_notice_dir)
                    return
        except http.client.HTTPException as e:
            print(f"SSL verification failed for {domain}{path} skipping the request: {e}", file=sys.stderr)
                                
        print(f"Failed to get license data for {dependency['Origin']}", file=sys.stderr)
        exit(1)
    #license data is a comma separated value line with columns: component, url, license
    # we are interested in the license column
    license = license_data.split(",")[2]
    if "Apache-2.0" in license:
        print(f"Found APACHE-2.0 license in {dependency['Origin']}")
        # pull the NOTICE file into a new owner_repo directory
        # the url to the LICENSE file is at the second column of the license_data
        # we replace the suffix of the url (LICENSE) by NOTICE to get the NOTICE file
        notice_url = license_data.split(",")[1].replace("LICENSE", "NOTICE")
        os.makedirs(f"{dependencies_notice_dir}/{dep_sanitized}", exist_ok=True)
        
        # go-licenses missconstruct the url for licenses on subprojects of the google-cloud-go. 
        # this project is a mono repo and LICENSES are not in the subprojects, they are in the root
        if "https://github.com/googleapis/google-cloud-go" in notice_url:
            notice_url = "https://raw.githubusercontent.com/googleapis/google-cloud-go/master/NOTICE"

        # if notice_url is a github url, we can download the NOTICE file using raw.githubusercontent.com
        if "github.com" in notice_url:
            notice_url = notice_url.replace("https://github.com", "https://raw.githubusercontent.com")
        os.system(f"wget {notice_url}")
        if Path(f"NOTICE").exists():
            os.system(f"mv NOTICE {dependencies_notice_dir}/{dep_sanitized}/NOTICE")
        # if nothing was downloaded, try to get the NOTICE.txt file from the repository instead
        if not Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
            os.system(f"wget {notice_url.replace('NOTICE', 'NOTICE.txt')}")
            if Path(f"NOTICE.txt").exists():
                os.system(f"mv NOTICE.txt {dependencies_notice_dir}/{dep_sanitized}/NOTICE")
    else:
        print(f"License of {dependency['Origin']} is not APACHE-2.0", file=sys.stderr)

    # go-licenses save artifacts for the package for debug purposes only
    os.system(f"go-licenses save {dependency['Origin']} --save_path {temp_debug_dir}/{dep_sanitized}_go_licenses_pull")


def is_apache_2_license(license):
    # Check if the license is Apache 2.0
    return ("Apache License" in license and "Version 2.0" in license) or "Apache-2.0" in license

def get_github_owner_repo(repo_url):
    # Regular expression to match GitHub URLs and extract owner and repo
    if repo_url.startswith("github.com"):
        repo_url = repo_url.replace("github.com", "https://github.com")
    if repo_url.startswith("git://"):
        repo_url = repo_url.replace("git://", "https://")
    if repo_url.startswith("git+https://"):
        repo_url = repo_url.replace("git+https://", "https://")
    if repo_url.startswith("git+ssh://git@"):
        repo_url = repo_url.replace("git+ssh://git@", "https://")
    match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', repo_url)
    if match:
        owner = match.group(1)
        repo = match.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo
    else:
        raise ValueError("Invalid GitHub URL: " + repo_url)

def get_gitlab_owner_repo(repo_url):
    # Regular expression to match GitLab URLs and extract owner and repo
    if repo_url.startswith("gitlab.com"):
        repo_url = repo_url.replace("gitlab.com", "https://gitlab.com")
    match = re.match(r'https?://gitlab\.com/([^/]+)/([^/]+)', repo_url)
    if match:
        owner = match.group(1)
        repo = match.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo
    else:
        raise ValueError("Invalid GitLab URL: " + repo_url)
    
def setup_repository(owner, repo, tmp_repo_dir, tmp_debug_dir):
    cwd = os.getcwd()
    os.chdir(tmp_repo_dir)
    # Clone the repository
    repo_dest = f"{owner}_{repo}"
    os.system(f"git clone --recurse-submodules https://github.com/{owner}/{repo} {repo_dest}")
    os.chdir(cwd)

def setup_for_go_licenses(owner, repo, tmp_repo_dir, tmp_debug_dir):
    cwd = os.getcwd()
    os.chdir(tmp_repo_dir)
    repo_dest = f"{owner}_{repo}"
    os.chdir(repo_dest)
    #populate the go modules for later use
    os.system("go mod download")
    # the line below is only for debug purposes the go-licenses command fails for multitarget projects
    os.system(f"go-licenses csv . > {cwd}/{tmp_debug_dir}/{repo_dest}_licenses.csv")
    os.chdir(cwd)

def setup_for_npm_licenses(owner, repo, tmp_repo_dir, tmp_debug_dir):
    cwd = os.getcwd()
    os.chdir(tmp_repo_dir)
    repo_dest = f"{owner}_{repo}"
    os.chdir(repo_dest)
    # if there is no package json it is not a JS project, skip
    if Path("package.json").exists():
        # Install npm dependencies and license-report
        os.system("npm install -g license-report")
        os.system("npm install")
        # Generate the license report
        os.system(f"echo 'y' | npx license-checker -y --json >{cwd}/{tmp_debug_dir}/{repo_dest}_licenses.json")
    os.chdir(cwd)

def setup_for_cargo_licenses(owner, repo, tmp_repo_dir, tmp_debug_dir, rust_dependencies):
    cwd = os.getcwd()
    os.chdir(tmp_repo_dir)
    repo_dest = f"{owner}_{repo}"
    os.chdir(repo_dest)
    # if the temp repo doesn't have a cargo.toml file, we need to create one
    if not Path(f"Cargo.toml").exists():
        #initialize a new cargo project
        os.system("cargo init .")
        #add the dependency to the Cargo.toml file from the list in rust_dependencies using cargo add
        for dep in rust_dependencies:
            os.system(f"cargo add {dep['Origin']}")

    # Install cargo dependencies and generate license report
    os.system("cargo install cargo-license")
    cargo_deps_licenses = f"{cwd}/{tmp_debug_dir}/{repo_dest}_licenses.json"
    os.system(f"cargo license --json > '{cargo_deps_licenses}'")
    os.chdir(cwd)
    return cargo_deps_licenses


def get_dependencies(repo_url, temp_debug_dir):
    # Parse the repo_url to extract the owner and repo name
    owner, repo = get_github_owner_repo(repo_url)
    
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
    
        # Extract the dependencies from the sbom
        dependencies = []
        missed = [];
        for package in repo_sbom.get("sbom").get("packages"):
            if package.get("downloadLocation") == f"git+https://github.com/{owner}/{repo}":
                # This is the top level package
                origin = package.get("downloadLocation").replace("git+", "")
                type = "github"
            elif package.get("name").startswith("actions:"):
                continue # ignoring actions for now
            elif package.get("name").startswith("go:github.com"):
                origin = package.get("name").replace("go:", "https://")
                type = "github"
            elif package.get("name").startswith("go:"):
                origin = package.get("name").replace("go:", "")
                type = "gopkg"
            elif package.get("name").startswith("pip:"):
                origin = package.get("name").replace("pip:", "")
                type = "pip"
            elif package.get("name").startswith("rust:"):
                origin = package.get("name").replace("rust:", "")
                type = "rust"
            elif package.get("name").startswith("npm:"):
                origin = package.get("name").replace("npm:", "")
                type = "npm"
            elif package.get("name").startswith("rubygems:"):
                origin = package.get("name").replace("rubygems:", "")
                type = "gems"
            elif package.get("name").startswith("composer:"):
                origin = package.get("name").replace("composer:", "")
                type = "php"
            elif package.get("name").startswith("nuget:"):
                origin = package.get("name").replace("nuget:", "")
                type = "nuget"
            elif package.get("name").startswith("maven:"):
                origin = package.get("name").replace("maven:", "")
                type = "maven"
            else:
                missed.append(package.get("name")) 
                # Dump the missed package into stderr
                print(f"Missed package: {package}", file=sys.stderr)
                continue

            # Extract the package information
            package_info = {
                "Component": package['name'],
                "Origin": origin,
                "Version": package['versionInfo'],
                "Type": type,
                "License": package.get("licenseConcluded", None),
            }
            dependencies.append(package_info);
        total_missed_count = len(missed)
        print(f"Missed {total_missed_count} packages")
        # count how many where missed per domain prefix
        missed_count = {}
        for package in missed:
            domain = package.split("/")[0]
            if domain in missed_count:
                missed_count[domain] += 1
            else:
                missed_count[domain] = 1
        print("Missed packages per domain prefix:")
        print(json.dumps(missed_count, indent=4))
        with open(f"{temp_debug_dir}/{owner}_{repo}_missed_packages_debug.json", 'w') as f:
            f.write(json.dumps(missed, indent=4))
        with open(f"{temp_debug_dir}/{owner}_{repo}_all_dependencies_debug.json", 'w') as f:
            f.write(json.dumps(dependencies, indent=4))
        return dependencies
    else:
        # Print that there is no repository information and exit on error
        print("\033[91mNo repository information found\033[0m", file=sys.stderr)
        exit(1)

def get_nuget_package_info(package_id, version):
    #skip troubling packages with known licenses checked by hand
    if package_id == "Oktokit.graphQL":
        package_id = "graphql"
    package_id = package_id.lower()
    conn = http.client.HTTPSConnection("api.nuget.org")
    conn.request("GET", f"/v3/registration5-semver1/{package_id}/{version}.json")
    response = conn.getresponse()
    
    if response.status != 200:
        #extract source repository link from the website in nuget.org/packages/{package_id} by scrapping
        conn = http.client.HTTPSConnection("www.nuget.org")
        conn.request("GET", f"/packages/{package_id}")
        response = conn.getresponse()
        if response.status != 200:
            print(f"Failed to get information for package {package_id}")
            exit(1)
        package_info = response.read().decode("utf-8")
        # search for the repository url, it is in a <a> tag that has the title "View the source code for this package"
        # here is an example of the html structure to match
        # <a href="https://github.com/apache/logging-log4net" data-track="outbound-repository-url" title="View the source code for this package" rel="nofollow">
        match = re.search(r'<a href="([^"]+)" data-track="outbound-repository-url" title="View the source code for this package" rel="nofollow">', package_info)
        if match:
            repository = match.group(1)
        else:
            print(f"Failed to get repository for package {package_id}")
            exit(1)
        # search for the license url, it is in a <a> tag that has the href url starts with "https://licenses.nuget.org"
        # here is an example of the html structure to match
        # <a href="https://licenses.nuget.org/Apache-2.0" aria-label="License Apache-2.0">Apache-2.0</a>
        match = re.search(r'<a href="https://licenses.nuget.org/([^"]+)" aria-label="License [^"]+">[^<]+</a>', package_info)
        if match:
            license = f"https://licenses.nuget.org/{match.group(1)}"
        else:
            license = None
        return {
            "license": license,
            "repository": repository
        }

    
    package_info = json.loads(response.read().decode("utf-8"))

    # retrieve nuspec file package metadata using the package info
    catalog_url = package_info['catalogEntry']
    catalog_domain = catalog_url.split("/")[2]
    catalog_path = "/" + "/".join(catalog_url.split("/")[3:])

    conn = http.client.HTTPSConnection(catalog_domain)
    conn.request("GET", catalog_path)
    response = conn.getresponse()
    if response.status != 200:
        print(f"Failed to get information for package {package_id}")
        exit(1)
    
    catalog_entry = json.loads(response.read().decode("utf-8"))

    #if the licenseUrl key is present use it, otherwise get projectUrl instead
    if "licenseUrl" in catalog_entry:
        license = catalog_entry["licenseUrl"]
    elif "projectUrl" in catalog_entry:
        license = catalog_entry["projectUrl"]
    else:
        print(f"Failed to get license for package {package_id}")
        exit(1)
    if license == "https://aka.ms/deprecateLicenseUrl":
        license = catalog_entry["licenseFile"]
    repository_url = catalog_entry.get("repository")
    return {
        "license": license,
        "repository": repository_url
    }


def download_notices_from_nuget(dependency, dependencies_notice_dir):
    #Skipping known by github licensed dependencies that are not APACHE-2.0
    if dependency['License'] != None and not is_apache_2_license(dependency['License']):
        print(f"Skipping {dependency['Origin']} as it is known to not have APACHE-2.0 license")
        return
    # Skipping .net components
    if dependency['Origin'].startswith("Microsoft.NET.") or dependency['Origin'].startswith("Microsoft.") or dependency['Origin'].startswith("Newtonsoft."):
        print(f"Skipping {dependency['Origin']} as it is a .NET component")
        return
    if dependency['Origin'].startswith("System."):
        print(f"Skipping {dependency['Origin']} as it is a .NET component")
        return
    #skipping known not to be APACHE-2.0 licensed dependencies that are troublesome to read
    if dependency['Component'] in ["nuget:StatsdClient", "nuget:IBM.Data.DB2.iSeries", "nuget:Stub.System.Data.SQLite.Core.NetFramework"]:
        print(f"Skipping {dependency['Origin']} as it is known to not have APACHE-2.0 license") 
        return
    
    # skipping some known dependencies that are not recognized by nuget but manually checked to be apache without NOTICE
    if dependency['Component'] == "nuget:log4net.Ext.Json":
        print(f"Skipping {dependency['Origin']} as it is known to have APACHE-2.0 license without notice") 
        return

    # adding missing information on nuget metadata
    if dependency['Component'] == "nuget:Datadog.Sketches":
        dependency["Origin"] = "https://github.com/DataDog/sketches-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Datadog.Trace":
        dependency["Origin"] = "https://github.com/DataDog/dd-trace-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Serilog.Formatting.Compact":
        dependency["Origin"] = "https://github.com/serilog/serilog-formatting-compact"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] in ["nuget:OpenTelemetry.Extensions.Hosting", "nuget:OpenTelemetry", "nuget:OpenTelemetry.Api"]:
        dependency["Origin"] = "https://github.com/open-telemetry/opentelemetry-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] in ["nuget:OpenTelemetry.Instrumentation.Http", "nuget:OpenTelemetry.Instrumentation.AspNetCore"]:
        dependency["Origin"] = "https://github.com/open-telemetry/opentelemetry-dotnet-contrib"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:NLog":
        dependency["Origin"] = "https://github.com/NLog/NLog"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if "Avalonia" in dependency['Component']:
        dependency["Origin"] = "https://github.com/AvaloniaUI/Avalonia"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Grpc":
        dependency["Origin"] = "https://github.com/grpc/grpc"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:RabbitMQ.Client":
        dependency["Origin"] = "https://github.com/rabbitmq/rabbitmq-dotnet-client"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:log4net":
        dependency["Origin"] = "https://github.com/apache/logging-log4net"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Aerospike.Client":
        dependency["Origin"] = "https://github.com/aerospike/aerospike-client-csharp"
        dependency["License"] = "Apache-2.0"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Grpc.AspNetCore":
        dependency["Origin"] = "https://github.com/grpc/grpc-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:CouchbaseNetClient":
        dependency["Origin"] = "https://github.com/couchbase/couchbase-net-client"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:Selenium.WebDriver":
        dependency["Origin"] = "https://github.com/SeleniumHQ/selenium"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:xunit.extensibility.execution":
        dependency["Origin"] = "https://github.com/xunit/xunit"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:xunit.analyzers":
        dependency["Origin"] = "https://github.com/xunit/xunit.analyzers"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:Serilog":
        dependency["Origin"] = "https://github.com/serilog/serilog"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:Datadog.Trace.Bundle":
        dependency["Origin"] = "https://github.com/DataDog/dd-trace-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:Serilog.Extensions.Logging":
        dependency["Origin"] = "https://github.com/serilog/serilog-extensions-logging"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:Serilog.Sinks.File":
        dependency["Origin"] = "https://github.com/serilog/serilog-sinks-file"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:JetBrains.Profiler.SelfApi":
        dependency["Origin"] = "https://github.com/JetBrains/profiler-self-api"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:libddwaf":
        dependency["Origin"] = "https://github.com/datadog/libddwaf"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:DiffPlex":
        dependency["Origin"] = "https://github.com/mmanela/diffplex.git"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'].startswith("nuget:SQLitePCLRaw"):
        dependency["Origin"] = "https://github.com/ericsink/SQLitePCL.raw"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'].startswith("nuget:Dapper"):
        dependency["Origin"] = "https://github.com/DapperLib/Dapper"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:Serilog.Expressions":
        dependency["Origin"] = "https://github.com/serilog/serilog-expressions"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:Serilog.Settings.Configuration":
        dependency["Origin"] = "https://github.com/serilog/serilog-settings-configuration"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'].startswith("nuget:OpenTelemetry."):
        dependency["Origin"] = "https://github.com/open-telemetry/opentelemetry-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:xunit.runner.visualstudio":
        dependency["Origin"] = "https://github.com/xunit/visualstudio.xunit"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'].startswith("nuget:Grpc"):
        dependency["Origin"] = "https://github.com/grpc/grpc"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:EntityFramework":
        dependency["Origin"] = "https://github.com/dotnet/ef6"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'] == "nuget:RestSharp":
        dependency["Origin"] = "https://github.com/restsharp/RestSharp"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return     
    if dependency['Component'] == "nuget:NewRelic.Agent.Api":
        dependency["Origin"] = "https://github.com/newrelic/newrelic-dotnet-agent"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return    
    if dependency['Component'].startswith("nuget:MassTransit"):
        dependency["Origin"] = "https://github.com/MassTransit/MassTransit"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Confluent.Kafka":
        dependency["Origin"] = "https://github.com/confluentinc/confluent-kafka-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'].startswith("nuget:MongoDB.Driver"):
        dependency["Origin"] = "https://github.com/mongodb/mongo-csharp-driver"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Amazon.Lambda.RuntimeSupport":
        dependency["Origin"] = "https://github.com/aws/aws-lambda-dotnet"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'].startswith("nuget:AWSSDK"):
        dependency["Origin"] = "https://github.com/aws/aws-sdk-net"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:MySql.Data":
        dependency["Origin"] = "https://github.com/mysql/mysql-connector-net"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:ServiceStack.Redis":
        dependency["Origin"] = "https://github.com/ServiceStack/ServiceStack"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency['Component'] == "nuget:Owin":
        dependency["Origin"] = "https://github.com/owin-contrib/owin-hosting"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency["Component"] == "nuget:WebActivator":
        dependency["Origin"] = "https://github.com/davidebbo/WebActivator"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    if dependency["Component"] == "nuget:immutables":
        dependency["Origin"] = "https://github.com/MagicStack/immutables"
        download_notices_for_github_project(dependency, dependencies_notice_dir)
        return
    
    # MIT licensed
    if dependency['Component'].startswith("nuget:IndieSystem"):
        print(f"Skipping {dependency['Origin']} as it is impossible to find")
        return

    # get package metadata using nuget show
    info = get_nuget_package_info(dependency['Origin'], dependency['Version'])

    #adding missed repository info
    if dependency['Component'] == "nuget:xunit":
        info["repository"] = "https://github.com/xunit/xunit"
    if dependency['Component'] == "nuget:FluentAssertions":
        info["repository"] = "https://github.com/fluentassertions/fluentassertions"
    if dependency['Component'] in ["nuget:NuGet.CommandLine", "nuget:NuGet.Protocol", "nuget:NuGet.Build.Tasks", "nuget:NuGet.Build.Tasks.Pack"]:
        info["repository"] = "https://github.com/NuGet/NuGet.Client"
    if dependency['Component'] == "nuget:DiffMatchPatch":
        info["repository"] = "https://github.com/google/diff-match-patch"
    if dependency['Component'] == "nuget:Elasticsearch.Net":
        info["repository"] = "https://github.com/elastic/elasticsearch-net"

    # Extract the license information from the metadata
    if info["license"] is None:
        exit(1)
    if not is_apache_2_license(info["license"]):
        print(f"License of {dependency['Origin']} is not APACHE-2.0", file=sys.stderr)
        return
    dependency["Origin"] = info["repository"]

    if not info["repository"]:
        print(f"Failed to get repository for package {dependency['Origin']}")
        exit(1)

    if "github.com" in info["repository"]:
        download_notices_for_github_project(dependency, dependencies_notice_dir)  
        return
    if "gitlab.com" in info["repository"]:
        download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
        return
    print(f"Unknown repository URL: {info['repository']}", file=sys.stderr)
    exit(1)
    

def download_notices_from_php(dependency, dependencies_notice_dir):
    # Special cases
    #extensions are php requirements, not installed packages
    if dependency["Origin"].startswith("ext-") or dependency["Origin"].startswith("lib-"):
        print(f"Skipping {dependency['Origin']} as it is a PHP extension")
        return
    
    if dependency["Origin"] == "php":
        print(f"Skipping {dependency['Origin']} as it is the PHP language")
        return
    
    if dependency["Origin"].startswith("composer-"):
        print(f"Skipping {dependency['Origin']} as it is a composer plugin requirement")
        return
    
    if dependency["Origin"].startswith("fixtures/drupal"):
        print(f"Skipping {dependency['Origin']} as it is a Drupal fixture")
        return

    # get package metadata using composer show
    result = subprocess.run(f"composer show --all --format=json {dependency['Origin']}", shell=True, capture_output=True, text=True)
    license = None
    if result.returncode == 0:
        package_info = json.loads(result.stdout)
        license = []
        for l in package_info.get("licenses"):
            license.append(l["osi"])
            if l['name'].startswith("Apache") or l['name'].startswith("apache") or l['name'].startswith("APACHE"):
                continue
        
    if not license or is_apache_2_license(license):
        repo_url = package_info["source"]["url"]
        owner, repo = get_github_owner_repo(repo_url)
        dep_sanitized = dependency["Origin"].replace("/", "_")
        # Check if the NOTICE file already exists
        if Path(f"{dependencies_notice_dir}/{dep_sanitized}/NOTICE").exists():
            print(f"NOTICE file for {owner}/{repo} already downloaded")
            return
        # Download the NOTICE file from the repository
        dependency["Origin"] = repo_url
        dependency["License"] = license
        if "github.com" in repo_url:
            download_notices_for_github_project(dependency, dependencies_notice_dir)
        elif "gitlab.com" in repo_url:
            download_notices_for_gitlab_project(dependency, dependencies_notice_dir)
        else:
            print(f"Unknown repository URL: {repo_url}", file=sys.stderr)
            exit(1)
    return

def download_notices_from_java_gradle_dependencies(temp_repo, dependencies_notice_dir):
    # Get the dependencies of the project from parsing the radle.lockfile file
    try:
        with open(f"{temp_repo}/gradle.lockfile") as f:
            build_file = f.read()
    except FileNotFoundError:
        print(f"gradle.lockfile not found in {temp_repo}", file=sys.stderr)
        return
    # Extract the dependencies
    for line in build_file.splitlines():
        if line.startswith("#") or not line.strip() or line.startswith("empty="):
            continue
        #extract the dependency information from the line
        match = re.match(r"^\s*([^\s:]+):([^\s:]+):([^\s:]+)=", line)
        if match:
            group = match.group(1)
            if group == "commons-codec":
                group = "org.apache.commons"
            name = match.group(2)
            version = match.group(3)
            if group == "info.picocli" and name == "picocli":
                download_notices_for_github_project({
                    "Component": f"{group}:{name}",
                    "Origin": f"https://github.com/remkop/picocli",
                    "Version": version
                }, dependencies_notice_dir)
                continue
            if group == "jaxen":
                group = "com.github.jaxen-xpath"
            if name == "jna":
                group = "com.github.java-native-access"
            if name == "jcip-annotations":
                group = "com.github.stephenc"
            if group == "net.sf.saxon":
                continue # Non-OSI approved license
            if group == "org.checkerframework":
                group = "com.github.typetools"
                name = "checker-framework"
            if "codehaus" in group:
                group = "com.github.mojohaus"
            if name.endswith("-annotations") and "stephenc" not in group:
                name = name[:-12]
            if group == "org.dom4j" and name == "dom4j":
                group = "com.github.dom4j"
            if group.startswith("org.ec4j") and name.startswith("ec4j-"):
                name = "ec4j"
                group = "com.github.ec4j"
            if group.startswith("org.jetbrains"):
                group = "com.github.jetbrains"
                if name == "annotations":
                    name = "JetBrains.Annotations"
            if name.startswith("kotlin-") and owner == "jetbrains":
                name = "kotlin"
            if name == "jline":
                group = "com.github.jline"
                name = "jline3"
            if group == "org.junit" and name.startswith("junit"):
                group = "com.github.junit-team"
                name = "junit5"
            if group == "org.ow2.asm" and name.startswith("asm"):
                continue #BSD-3-Clause
            if group == "org.scalameta":
                group = "com.github.scalameta"
                if "parse" in name:
                    name = "fastparse"
                    continue # MIT license
                if name.startswith("common"):
                    name = "scalameta"
                if "fmt" in name:
                    name = "scalafmt"
            if group.startswith("org.scala-lang"):
                group = "com.github.scala"
                name = "scala"
            if group == "org.slf4j":
                group = "com.github.qos-ch"
                name = "slf4j"
            if group == "org.xmlresolver":
                group = "com.github.xmlresolver"
            if group == "org.typelevel":
                group = "com.github.typelevel"
                if name.startswith("paiges"):
                    name = "paiges"
            if group == "xml-apis":
                continue # Non-OSI approved license
            #remove suffix after _ if the anme contains it
            if re.search(r"_\d", name):
                name = re.sub(r"_\d.*", "", name)
            
            # Check if the dependency is a Maven dependency
            if group.startswith("com.") or group.startswith("org."):
                # Check if the dependency is a GitHub dependency
                if group.startswith("com.github."):
                    owner = group[11:]
                    repo = name
                    #corrections
                    if owner.startswith("shyiko"):
                        owner = "shyiko"
                        if repo == "klob":
                            continue # MIT license
                    if repo.startswith("spotbugs-"):
                        repo = "spotbugs"
                    # Download the NOTICE file from the repository
                    download_notices_for_github_project({
                        "Component": f"{group}:{name}",
                        "Origin": f"https://github.com/{owner}/{repo}",
                        "Version": version
                    }, dependencies_notice_dir)
                    continue
                if group.startswith("com.google."):
                    if name == "jsr305":
                        continue # GPL-2.0
                    if group == "com.google.guava":
                        name = "guava"
                    if name.startswith("error_prone") or name == "javac-shaded":
                        name = "error-prone"
                    download_notices_for_github_project({
                            "Component": f"{group}:{name}",
                            "Origin": f"https://github.com/google/{name}",
                            "Version": version
                    }, dependencies_notice_dir)
                    continue
                if group.startswith("com.pinterest"):
                    if name == "ktlint" or group == "com.pinterest.ktlint":
                        download_notices_for_github_project({
                                "Component": f"{group}:{name}",
                                "Origin": f"https://github.com/pinterest/ktlint",
                                "Version": version
                        }, dependencies_notice_dir)
                        continue
                if group == "com.lihaoyi":
                    download_notices_for_github_project({
                            "Component": f"{group}:{name}",
                            "Origin": f"https://github.com/com-lihaoyi/{name}",
                            "Version": version
                    }, dependencies_notice_dir)
                    continue
                if group == "org.eclipse.platform":
                    continue # Eclipse Public License
                if name.startswith("spotless-eclipse-"):
                    continue # Eclipse Public License
                if line.startswith("com.geirsson:metaconfig"):
                    download_notices_for_github_project({
                            "Component": f"{group}:{name}",
                            "Origin": f"https://github.com/scalameta/metaconfig"
                    }, dependencies_notice_dir)
                    continue
                if group == "com.typesafe":
                    group = "com.lightbend"
                    download_notices_for_github_project({
                            "Component": f"{group}:{name}",
                            "Origin": f"https://github.com/lightbend/{name}",
                            "Version": version
                    }, dependencies_notice_dir)
                    continue
                if group.startswith("org.apache"):
                    if name == "bcel":
                        name = "commons-bcel"
                    if name == "commons-lang3":
                        name = "commons-lang"
                    if name == "httpclient5":
                        name = "httpcomponents-client"
                    if name.startswith("httpcore5"):
                        name = "httpcomponents-core"
                    if name.startswith("log4j"):
                        name = "log4j"
                    download_notices_for_github_project({
                            "Component": f"{group}:{name}",
                            "Origin": f"https://github.com/apache/{name}",
                            "Version": version
                    }, dependencies_notice_dir)
                    continue
        print(f"Unknown dependency: {line}", file=sys.stderr)
        exit(1)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Fetch from NOTICE files from all projects that are a dependecy declared in the github SBOM of the project.")
    parser.add_argument("repo_urls", nargs='+', help="The URLs of the GitHub repositories")
    
    # Parse arguments
    args = parser.parse_args()
    
    # create a temp directory for repos to be downloaded
    os.makedirs("tmp_repos", exist_ok=True)

    # Create a temp directory for debuging_files
    os.makedirs("tmp_debug", exist_ok=True)

    for repo_url in args.repo_urls:
        # create directory with a sanitized name of the repo
        owner, repo = get_github_owner_repo(repo_url)
        setup_repository(owner, repo, "tmp_repos", "tmp_debug")

        # Get the dependencies of the repository from github
        dependencies = get_dependencies(repo_url, "tmp_debug")

        github_dependencies = [d for d in dependencies if d["Type"] == "github"]
        gopkg_dependencies = [d for d in dependencies if d["Type"] == "gopkg"]
        pip_dependencies = [d for d in dependencies if d["Type"] == "pip"]
        rust_dependencies = [d for d in dependencies if d["Type"] == "rust"]
        npm_dependencies = [d for d in dependencies if d["Type"] == "npm"]
        ruby_dependencies = [d for d in dependencies if d["Type"] == "gems"]
        php_dependencies = [d for d in dependencies if d["Type"] == "php"]
        dotnet_dependencies = [d for d in dependencies if d["Type"] == "nuget"]
        java_dependencies = [d for d in dependencies if d["Type"] == "maven"]

        # setup package manager specific tools
        if len(gopkg_dependencies) > 0:
            setup_for_go_licenses(owner, repo, "tmp_repos", "tmp_debug")
        if len(npm_dependencies) > 0:
            setup_for_npm_licenses(owner, repo, "tmp_repos", "tmp_debug")
        if len(rust_dependencies) > 0:
            cargo_deps_licenses = setup_for_cargo_licenses(owner, repo, "tmp_repos", "tmp_debug", rust_dependencies)

        # Create directory to save the notices
        os.makedirs("notice_files", exist_ok=True)
        os.makedirs(f"notice_files/{owner}_{repo}", exist_ok=True)
        #copy notice file from repo to the notice_files directory
        os.system(f"cp tmp_repos/{owner}_{repo}/NOTICE notice_files/{owner}_{repo}/NOTICE")
        #create dependencies directory
        dependencies_notice_dir = f"notice_files/{owner}_{repo}/dependencies"
        os.makedirs(dependencies_notice_dir, exist_ok=True)
        # create python virtal environment
        os.system("python3 -m venv venv")
        # activate the virtual environment
        os.system("source venv/bin/activate")

        # Extract the location of the packages and download the NOTICE files
        for dependency in dotnet_dependencies:
            download_notices_from_nuget(dependency, dependencies_notice_dir)

        for dependency in php_dependencies:
            download_notices_from_php(dependency, dependencies_notice_dir)
        
        for dependency in gopkg_dependencies:
            # skip own repo, its already checked in the github section
            if f"{owner}/{repo}" in dependency["Origin"]:
                continue
            download_notices_for_gopkg_project(dependency, f"tmp_repos/{owner}_{repo}", dependencies_notice_dir, temp_debug_dir="tmp_debug")

        for dependency in github_dependencies:
            download_notices_for_github_project(dependency, dependencies_notice_dir)

        for dependency in rust_dependencies:
            download_notices_from_cargo(dependency, dependencies_notice_dir, cargo_deps_licenses)

        for dependency in pip_dependencies:
            download_notices_from_pip(dependency, dependencies_notice_dir)

        for dependency in npm_dependencies:
            download_notices_from_npm(dependency, dependencies_notice_dir)

        for dependency in ruby_dependencies:
            download_notices_from_ruby(dependency, dependencies_notice_dir)

        download_notices_from_java_gradle_dependencies(f"tmp_repos/{owner}_{repo}", dependencies_notice_dir)

        cwd = os.getcwd()
        # Find all directories that contain NOTICE files
        notice_files = subprocess.check_output("find notice_files/{owner}_{repo} -name NOTICE", shell=True).decode().splitlines()
        # tar-gz the notice_files directory skipping all directories that are empty
        with open(f"notice_files/{owner}_{repo}_notice_files.tar.gz", "wb") as tar_file:
            subprocess.run(["tar", "-czf", "-", *notice_files], stdout=tar_file)


if __name__ == "__main__":
    main()