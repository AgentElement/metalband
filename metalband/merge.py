import csv
import argparse
import sys


def find_last_cited_year(input_path, output_path):
    """
    Reads a TSV file of citations and produces a TSV file of cited papers
    and the year they were last cited.

    Args:
        input_path (str): The path to the input TSV file.
        output_path (str): The path where the output TSV file will be saved.
    """
    print(f"Reading data from: {input_path}")

    # This dictionary will store {Cited_DOI: Last_Cited_Year}
    last_cited_data = {}

    try:
        with open(input_path, "r", encoding="utf-8", newline="") as infile:
            # Use csv.reader for robust handling of tab-separated values
            reader = csv.reader(infile, delimiter="\t")

            # Read and verify the header
            header = next(reader)
            expected_header = ["Citing_DOI", "Citing_Year", "Cited_DOI", "Cited_Year"]
            if header != expected_header:
                print(
                    f"Warning: Unexpected header format. Found: {header}",
                    file=sys.stderr,
                )
                print(f"Expected: {expected_header}", file=sys.stderr)

            # Process each citation record
            for i, row in enumerate(reader, 1):
                # Basic validation for row structure
                if len(row) != 4:
                    print(
                        f"Warning: Skipping malformed row #{i}: {row}", file=sys.stderr
                    )
                    continue

                try:
                    citing_year_str = row[1]
                    cited_doi = row[2]

                    # Ensure the year is a valid integer
                    citing_year = int(citing_year_str)

                    # Update the dictionary if this DOI is new or the citation is more recent
                    if (
                        cited_doi not in last_cited_data
                        or citing_year > last_cited_data[cited_doi]
                    ):
                        last_cited_data[cited_doi] = citing_year

                except (ValueError, IndexError):
                    # Handle cases where the year is not a number or row is malformed
                    print(
                        f"Warning: Skipping row #{i} due to data error: {row}",
                        file=sys.stderr,
                    )
                    continue

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Processed {len(last_cited_data)} unique cited papers.")
    print(f"Writing results to: {output_path}")

    # Write the aggregated data to the output file
    with open(output_path, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile, delimiter="\t")

        # Write the header
        writer.writerow(["Cited_DOI", "Last_Cited_Year"])

        # Write the data, sorted by DOI for consistent output
        for doi, year in sorted(last_cited_data.items()):
            writer.writerow([doi, year])

    print("Done.")


def main():
    """Main function to parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Find the last cited year for each paper from a citation graph TSV file.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        help="Path to the input TSV file.\nFormat: Citing_DOI\tCiting_Year\tCited_DOI\tCited_Year",
    )
    parser.add_argument(
        "output_file",
        help="Path for the output TSV file.\nFormat: Cited_DOI\tLast_Cited_Year",
    )

    args = parser.parse_args()
    find_last_cited_year(args.input_file, args.output_file)


if __name__ == "__main__":
    main()

