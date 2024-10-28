# ospo-tools

A set of tools mantained by ospo to work with open source projects

## generate_3rdparty-csv

This is a tool to generate 3party-license csv files used to track dependencies licenses.

As Today, only golang is supported. We plan to expand to other languages soon.

This tool collects license and other metadata information using multiple sources, including the GitHub API and the go-licenses package.
It supports gathering data from various repositories to generate a comprehensive 3rd-party license CSV file.
Because, these tools require calls to public APIs, and the APIs may trottle down based in usage, it is spected that run takes many minutes depeding mostly in the size of the project dependency tree.

### requirements

- python3 - [Python install instructions](https://www.python.org/downloads/)
- gopkg - [GoLang and GoPkg install instructions](https://go.dev/doc/install)
- go-licenses - [GoLicenses install instructions](https://go.dev/doc/install)

### usage

To install and run the command after cloning the repository:

```bash
#starting at the root of the repository
#create and activate a venv
python3 -m venv venv
source venv/bin/activate
pip install .

# Optionally you can define a GITHUB_TOKEN, if used it will raise the throttling threashold and maspeed up your generation calls to github APIs.
export GITHUB_TOKEN=YOUR_TOKEN
venv/bin/generate_3rd_party_csv https://github.com/owner/repo > LICENSE-3rdparty.csv
```

### current state

- Initial set of dependencies is collected via github-sbom api.
- Action packages are ignored.
- Go packages use multiple heuristics to enrich information by scrapping websites until reaching a source-code repository in GitHub if available.
- All package that are traced back to github (go or not) will try to nerich information for license and copyright, for copyright when nothing else is available, the github-owner is assigned.
