import csv
import requests
import time
import argparse  # Import argparse


# Function to search for DOI using CrossRef API
def find_doi_crossref(title, authors, year=None, conference=None):
    """
    Searches for a DOI using the CrossRef API.
    """
    base_url = "https://api.crossref.org/works"
    params = {"query.bibliographic": f"{title} {authors}", "rows": 1}
    if year:
        params["filter"] = f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"

    headers = {"User-Agent": "DOI Pyscript/1.0"}

    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("message", {}).get("items"):
            item = data["message"]["items"][0]
            if "title" in item and item["title"]:
                if title.lower().startswith(item["title"][0].lower()[:30]):
                    return item.get("DOI")
            elif "DOI" in item:
                return item.get("DOI")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  CrossRef API request error: {e}")
        return None
    except ValueError:
        print("  CrossRef API response was not valid JSON.")
        return None


# Function to search for DOI using OpenAlex API
def find_doi_openalex(title, authors, year=None, conference=None):
    """
    Searches for a DOI using the OpenAlex API.
    """
    base_url = "https://api.openalex.org/works"
    search_query = (
        f"title.search:{title} AND author.search:{authors.split(',')[0].split()[-1]}"
    )
    params = {"search": search_query, "per_page": 1}
    if year:
        params["filter"] = f"publication_year:{year}"

    headers = {"User-Agent": "DOI Pyscript/1.0"}

    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("results"):
            item = data["results"][0]
            if item.get("doi"):
                return item["doi"].replace("https://doi.org/", "")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  OpenAlex API request error: {e}")
        return None
    except ValueError:
        print("  OpenAlex API response was not valid JSON.")
        return None


def process_tsv_file(filepath, output_filepath=None):
    """
    Reads a TSV file, searches for DOIs, and prints the results or saves to a file.
    Assumes TSV has columns: conference, authors, title, year
    """
    results = []
    header = ["conference", "authors", "title", "year", "DOI"]

    try:
        with open(filepath, "r", newline="", encoding="utf-8") as tsvfile:
            reader = csv.DictReader(tsvfile, delimiter="\t")
            if not all(
                field in reader.fieldnames
                for field in ["conference", "authors", "title", "year"]
            ):
                print(
                    f"Error: TSV file must contain 'conference', 'authors', 'title', and 'year' columns. Found: {reader.fieldnames}"
                )
                return

            print("Processing papers...")
            # Print header to console if not writing to file
            if not output_filepath:
                print("\t".join(header))
                print("----------\t-------\t-----\t----\t---")

            for row_number, row in enumerate(reader, 1):
                conference = row.get("conference", "").strip()
                authors = row.get("authors", "").strip()
                title = row.get("title", "").strip()
                year = row.get("year", "").strip()
                doi_found = "NOT_SEARCHED_MISSING_INFO"

                if not title or not authors:
                    print(
                        f"Skipping row {row_number} due to missing title or authors: {row}"
                    )
                    current_result = [conference, authors, title, year, doi_found]
                else:
                    print(f"Processing: '{title[:50]}...' by {authors.split(',')[0]}")
                    doi = None
                    print("  Trying CrossRef...")
                    doi = find_doi_crossref(title, authors, year, conference)
                    time.sleep(0.5)

                    if not doi:
                        print("  Not found in CrossRef. Trying OpenAlex...")
                        doi = find_doi_openalex(title, authors, year, conference)
                        time.sleep(0.5)

                    doi_found = doi if doi else "NOT_FOUND"
                    current_result = [conference, authors, title, year, doi_found]

                results.append(current_result)
                if not output_filepath:
                    print("\t".join(str(x) for x in current_result))

        if output_filepath:
            with open(output_filepath, "w", newline="", encoding="utf-8") as outfile:
                writer = csv.writer(outfile, delimiter="\t")
                writer.writerow(header)
                writer.writerows(results)
            print(f"\nResults saved to {output_filepath}")
        else:
            print("\nProcessing complete.")

    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Search for DOIs of papers listed in a TSV file."
    )
    parser.add_argument("filepath", help="Path to the input .tsv file.")
    parser.add_argument(
        "-o",
        "--output",
        help="Path to the output .tsv file to save results. If not provided, results are printed to console.",
        default=None,
    )

    args = parser.parse_args()

    process_tsv_file(args.filepath, args.output)
