import xml.etree.ElementTree as ET
import argparse
import gzip
import sys


def extract_doi_year(element):
    """
    Extracts DOI and year from a DBLP publication element.
    DOI is typically in an <ee> tag.
    Year is in a <year> tag.
    """
    doi = None
    year_str = None
    key = element.get("key")  # DBLP key

    for child in element:
        if child.tag == "ee" and child.text and "doi.org/" in child.text.lower():
            # Extract DOI, try to normalize it
            try:
                doi_text = child.text.lower()
                doi_start = doi_text.find("doi.org/") + len("doi.org/")
                doi = doi_text[doi_start:]
                # Remove potential trailing garbage if any (though less common for DOI itself)
                if " " in doi:
                    doi = doi.split(" ")[0]
            except Exception:
                pass  # Could not parse DOI from ee
        elif child.tag == "year" and child.text:
            year_str = child.text.strip()
            # Basic validation for a 4-digit year
            if not (len(year_str) == 4 and year_str.isdigit()):
                year_str = None  # Invalid year format

    # As a fallback for DOI, check <note type="doi">
    if not doi:
        for child in element:
            if child.tag == "note" and child.get("type") == "doi" and child.text:
                try:
                    doi_text = child.text.lower()
                    # Assuming the text of the note is the DOI itself
                    if "doi.org/" in doi_text:  # If it includes the full URL
                        doi_start = doi_text.find("doi.org/") + len("doi.org/")
                        doi = doi_text[doi_start:]
                    else:  # Assuming it's just the DOI string
                        doi = doi_text
                    if " " in doi:
                        doi = doi.split(" ")[0]
                except Exception:
                    pass

    if doi and year_str:
        return key, doi, year_str
    return (
        key,
        None,
        None,
    )  # Return key even if DOI/year is missing for citation resolution


def parse_dblp_xml(xml_file_path):
    """
    Parses the DBLP XML dump and extracts paper and citation information.

    Args:
        xml_file_path (str): Path to the DBLP XML file (can be .xml or .xml.gz).

    Returns:
        tuple: (all_papers, citation_links)
               all_papers: A dictionary mapping (doi, year) to DBLP key.
               citation_links: A list of tuples, where each tuple is
                               ((citing_doi, citing_year), (cited_doi, cited_year))
    """
    print(f"Starting parsing of {xml_file_path}...")

    all_papers_by_key = {}  # Stores {dblp_key: (doi, year)}
    all_papers_output = {}  # Stores {(doi, year): dblp_key} for the final output
    citation_relationships_by_key = []  # Stores (citing_key, cited_key_from_cite_tag)

    publication_tags = {
        "article",
        "inproceedings",
        "proceedings",
        "book",
        "incollection",
        "phdthesis",
        "mastersthesis",
        "www",
    }

    # Determine if the file is gzipped
    is_gzipped = xml_file_path.endswith(".gz")
    open_func = gzip.open if is_gzipped else open
    read_mode = (
        "rb" if is_gzipped else "r"
    )  # gzip needs binary, ET needs text for iterparse source

    context = ET.iterparse(xml_file_path, events=("start", "end"))
    # Get an iterator. In Python 3.8+ we can pass the file object directly to ET.iterparse.
    # For older versions, you might need to handle file opening and passing `source` carefully.
    # This example assumes direct path usage which works in recent Python versions.

    _, root = next(context)  # Get root element to clear it later

    processed_elements = 0
    relevant_elements = 0

    for event, elem in context:
        if event == "end" and elem.tag in publication_tags:
            processed_elements += 1
            if processed_elements % 500000 == 0:
                print(f"  Processed {processed_elements} top-level elements...")

            key, doi, year = extract_doi_year(elem)

            if key:  # Every publication should have a key
                if doi and year:
                    all_papers_by_key[key] = (doi, year)
                    all_papers_output[(doi, year)] = key
                    relevant_elements += 1

                # Look for <cite> tags (citations made by this paper)
                # The <cite> tag in DBLP often contains the DBLP key of the cited paper.
                for child in elem.findall("cite"):
                    cited_key = child.text
                    if cited_key:  # cited_key is the DBLP key of the paper being cited
                        # It might have a label like "... [SomeLabel12] Some Other Text"
                        # Or just "key_of_cited_paper"
                        # We assume for now it's mostly just the key or starts with the key
                        cited_key_cleaned = cited_key.split(" ")[0]  # Basic cleaning
                        citation_relationships_by_key.append((key, cited_key_cleaned))

            # Efficiently clear the element and its children from memory
            elem.clear()
            # Also clear the root reference to the element
            # This is crucial for large XML files to free memory
            # (From lxml documentation, similar principle applies to ElementTree's iterparse)
            # For ElementTree, clearing the parent's children list might be more direct if accessible,
            # but elem.clear() itself helps a lot.
            # Periodically, clearing children of the root can also help.
            if processed_elements % 10000 == 0:  # Adjust frequency as needed
                while (
                    root and root._children
                ):  # _children is internal, use with caution or find public API if available
                    root._children.pop(0)

    print(
        f"\nFinished initial parsing. Found {len(all_papers_by_key)} papers with keys."
    )
    print(f"Found {relevant_elements} papers with both DOI and Year.")
    print(
        f"Found {len(citation_relationships_by_key)} potential citation links (by DBLP key)."
    )

    # Resolve citation_relationships_by_key to DOI-based citation_links
    print("\nResolving citation links to (DOI, Year)...")
    citation_links_output = []
    resolved_citations = 0
    unresolved_citations_citing_missing = 0
    unresolved_citations_cited_missing = 0

    for citing_key, cited_key in citation_relationships_by_key:
        citing_paper_info = all_papers_by_key.get(citing_key)
        cited_paper_info = all_papers_by_key.get(cited_key)

        if citing_paper_info and cited_paper_info:
            # Both citing and cited papers have (DOI, Year)
            citation_links_output.append((citing_paper_info, cited_paper_info))
            resolved_citations += 1
        elif not citing_paper_info:
            unresolved_citations_citing_missing += 1
        elif not cited_paper_info:
            unresolved_citations_cited_missing += 1

        if (
            resolved_citations
            + unresolved_citations_citing_missing
            + unresolved_citations_cited_missing
        ) % 100000 == 0:
            print(
                f"  Processed {resolved_citations + unresolved_citations_citing_missing + unresolved_citations_cited_missing}/{len(citation_relationships_by_key)} raw citation links for DOI resolution..."
            )

    print(f"\nFinished resolving citations.")
    print(
        f"  Successfully resolved {resolved_citations} citations to (DOI, Year) for both ends."
    )
    print(
        f"  Citations where citing paper's DOI/Year was missing: {unresolved_citations_citing_missing}"
    )
    print(
        f"  Citations where cited paper's DOI/Year was missing (but citing was present): {unresolved_citations_cited_missing}"
    )

    return all_papers_output, citation_links_output


def main():
    parser = argparse.ArgumentParser(
        description="Parse DBLP XML and extract paper and citation lists by DOI and year."
    )
    parser.add_argument(
        "dblp_xml_file",
        help="Path to the DBLP XML file (e.g., dblp.xml or dblp.xml.gz)",
    )
    parser.add_argument(
        "--output_papers",
        default="all_papers_doi_year.txt",
        help="Output file for the list of all papers (DOI, Year).",
    )
    parser.add_argument(
        "--output_citations",
        default="citation_links_doi_year.txt",
        help="Output file for citation links ((Citing DOI, Citing Year) -> (Cited DOI, Cited Year)).",
    )

    args = parser.parse_args()

    if not (
        args.dblp_xml_file.endswith(".xml") or args.dblp_xml_file.endswith(".xml.gz")
    ):
        print("Error: DBLP file must be an .xml or .xml.gz file.", file=sys.stderr)
        sys.exit(1)

    try:
        all_papers, citation_links = parse_dblp_xml(args.dblp_xml_file)

        print(f"\nWriting list of all papers to {args.output_papers}...")
        with open(args.output_papers, "w", encoding="utf-8") as f_papers:
            f_papers.write("DOI\tYear\tDBLP_Key\n")
            for (doi, year), dblp_key in all_papers.items():
                f_papers.write(f"{doi}\t{year}\t{dblp_key}\n")
        print(f"Wrote {len(all_papers)} papers.")

        print(f"\nWriting citation links to {args.output_citations}...")
        with open(args.output_citations, "w", encoding="utf-8") as f_citations:
            f_citations.write("Citing_DOI\tCiting_Year\tCited_DOI\tCited_Year\n")
            for (citing_doi, citing_year), (cited_doi, cited_year) in citation_links:
                f_citations.write(
                    f"{citing_doi}\t{citing_year}\t{cited_doi}\t{cited_year}\n"
                )
        print(f"Wrote {len(citation_links)} citation links.")

        print("\nProcessing complete.")

    except FileNotFoundError:
        print(
            f"Error: DBLP XML file not found at {args.dblp_xml_file}", file=sys.stderr
        )
        sys.exit(1)
    except ET.ParseError as e:
        print(
            f"Error: Could not parse the XML file. It might be malformed or not a DBLP XML. Details: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
