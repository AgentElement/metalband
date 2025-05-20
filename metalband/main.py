import lxml.etree as ET
import argparse
import gzip
import sys
import os  # For checking path for user message


def extract_doi_year(element):
    """
    Extracts DOI and year from a DBLP publication element.
    DOI is typically in an <ee> tag.
    Year is in a <year> tag.
    """
    doi = None
    year_str = None
    key = element.get("key")

    ee_tags = element.findall("ee")
    for ee_tag in ee_tags:
        if ee_tag.text and "doi.org/" in ee_tag.text.lower():
            try:
                doi_text = ee_tag.text.lower()
                doi_start = doi_text.find("doi.org/") + len("doi.org/")
                doi = doi_text[doi_start:]
                if " " in doi:
                    doi = doi.split(" ")[0]
                break
            except Exception:
                pass

    year_tag = element.find("year")
    if year_tag is not None and year_tag.text:
        year_str = year_tag.text.strip()
        if not (len(year_str) == 4 and year_str.isdigit()):
            year_str = None

    if not doi:
        note_tags = element.findall("note")
        for note_tag in note_tags:
            if note_tag.get("type") == "doi" and note_tag.text:
                try:
                    doi_text = note_tag.text.lower()
                    if "doi.org/" in doi_text:
                        doi_start = doi_text.find("doi.org/") + len("doi.org/")
                        doi = doi_text[doi_start:]
                    else:
                        doi = doi_text
                    if " " in doi:
                        doi = doi.split(" ")[0]
                    break
                except Exception:
                    pass

    if doi and year_str:
        return key, doi, year_str
    return key, None, None


def parse_dblp_xml(xml_file_path):
    print(f"Starting parsing of {xml_file_path} with lxml...")
    print(
        f"IMPORTANT: Ensure 'dblp.dtd' is in the same directory as the XML file: '{os.path.dirname(os.path.abspath(xml_file_path))}'"
    )
    print(
        f"Or, if parsing from a stream (like .gz), ensure 'dblp.dtd' is in the current working directory: '{os.getcwd()}' if lxml can't find it relative to the stream's origin."
    )

    all_papers_by_key = {}
    all_papers_output = {}
    citation_relationships_by_key = []

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

    # Crucial parser arguments for lxml.etree.iterparse
    # load_dtd=True:       Instructs the parser to load the DTD. This is essential for resolving entities like ü.
    # resolve_entities=True: (Default is True) Instructs the parser to replace entity references with their definitions.
    # no_network=True:     Prevents network access for DTDs/entities (good for local files).
    iterparse_kwargs = {
        "load_dtd": True,
        "resolve_entities": True,  # Default is True, but explicit for clarity
        "no_network": True,  # Important for security and predictability with local DTDs
    }

    file_obj = None
    try:
        is_gzipped = xml_file_path.endswith(".gz")

        if is_gzipped:
            file_obj = gzip.open(xml_file_path, "rb")  # Open as binary stream
            # When parsing from a stream, lxml might not know the original file's path
            # to resolve the DTD. It might try CWD or rely on libxml2's search paths.
            # Having dblp.dtd in the CWD can sometimes help in such cases.
            context = ET.iterparse(
                file_obj,
                events=("end",),
                tag=list(publication_tags) + ["dblp"],
                **iterparse_kwargs,
            )
        else:
            # When parsing from a filename, lxml can use the file's directory
            # as the base for resolving the DTD (e.g., "dblp.dtd" in same dir).
            context = ET.iterparse(
                xml_file_path,
                events=("end",),
                tag=list(publication_tags) + ["dblp"],
                **iterparse_kwargs,
            )

        processed_elements = 0
        relevant_elements = 0

        for event, elem in context:
            if elem.tag in publication_tags:
                processed_elements += 1
                if processed_elements % 500000 == 0:
                    print(f"  Processed {processed_elements} publication elements...")

                key, doi, year = extract_doi_year(elem)

                if key:
                    if doi and year:
                        all_papers_by_key[key] = (doi, year)
                        all_papers_output[(doi, year)] = key
                        relevant_elements += 1

                    for child in elem.findall("cite"):
                        cited_key = child.text
                        if cited_key:
                            cited_key_cleaned = cited_key.split(" ")[0]
                            citation_relationships_by_key.append(
                                (key, cited_key_cleaned)
                            )

            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[elem.getparent().index(elem.getprevious())]

    except ET.XMLSyntaxError as e:
        print(f"lxml.etree.XMLSyntaxError: {e}", file=sys.stderr)
        print(
            "This error often means the DTD ('dblp.dtd') was not found or could not be processed, or the XML is malformed.",
            file=sys.stderr,
        )
        print(
            f"Please ensure 'dblp.dtd' is in the same directory as your XML file ('{os.path.dirname(os.path.abspath(xml_file_path))}') and that both files are valid.",
            file=sys.stderr,
        )
        if file_obj:
            file_obj.close()
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during parsing: {e}", file=sys.stderr)
        if file_obj:
            file_obj.close()
        sys.exit(1)
    finally:
        if file_obj:
            file_obj.close()

    print(
        f"\nFinished initial parsing. Found {len(all_papers_by_key)} papers with keys."
    )
    print(f"Found {relevant_elements} papers with both DOI and Year.")
    print(
        f"Found {len(citation_relationships_by_key)} potential citation links (by DBLP key)."
    )

    print("\nResolving citation links to (DOI, Year)...")
    citation_links_output = []
    resolved_citations = 0
    unresolved_citations_citing_missing = 0
    unresolved_citations_cited_missing = 0
    total_raw_citations = len(citation_relationships_by_key)

    for i, (citing_key, cited_key) in enumerate(citation_relationships_by_key):
        citing_paper_info = all_papers_by_key.get(citing_key)
        cited_paper_info = all_papers_by_key.get(cited_key)

        if citing_paper_info and cited_paper_info:
            citation_links_output.append((citing_paper_info, cited_paper_info))
            resolved_citations += 1
        elif not citing_paper_info and cited_paper_info:
            unresolved_citations_citing_missing += 1
        elif citing_paper_info and not cited_paper_info:
            unresolved_citations_cited_missing += 1

        if (i + 1) % 500000 == 0:
            print(
                f"  Processed {i + 1}/{total_raw_citations} raw citation links for DOI resolution..."
            )

    print("\nFinished resolving citations.")
    print(
        f"  Successfully resolved {resolved_citations} citations to (DOI, Year) for both ends."
    )
    print(
        f"  Citations where citing paper's (DOI, Year) was missing from our extracted list: {unresolved_citations_citing_missing}"
    )
    print(
        f"  Citations where cited paper's (DOI, Year) was missing from our extracted list (but citing was present): {unresolved_citations_cited_missing}"
    )

    return all_papers_output, citation_links_output


def main():
    parser = argparse.ArgumentParser(
        description="Parse DBLP XML with lxml and extract paper and citation lists by DOI and year."
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

    # Check if DTD is present (basic check)
    xml_dir = os.path.dirname(os.path.abspath(args.dblp_xml_file))
    dtd_path = os.path.join(xml_dir, "dblp.dtd")
    if not os.path.exists(dtd_path):
        print(
            f"Warning: 'dblp.dtd' not found at expected location: {dtd_path}",
            file=sys.stderr,
        )
        print(
            "The DTD is required for resolving XML entities. Parsing might fail or be incorrect.",
            file=sys.stderr,
        )
        # Allow to proceed, parser will error out if DTD is strictly needed by the XML content.
    else:
        print(f"Found 'dblp.dtd' at: {dtd_path}")

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
    except Exception as e:
        print(f"An unexpected error occurred in main: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
