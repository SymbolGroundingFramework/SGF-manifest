import json
from rdflib import Graph, Namespace

g = Graph()
print("Loading file...")
g.parse("wikipedia_abstracts.ttl", format="turtle")

# Use the correct predicate: rdfs:comment
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
data = {}

count = 0
for s, p, o in g.triples((None, RDFS.comment, None)):
    if o.language == "en":
        uri = str(s)
        article_name = uri.replace("http://dbpedia.org/resource/", "")
        data[article_name] = str(o)
        count += 1
        if count % 50000 == 0:
            print(f"  Processed {count} articles...")

print(f"Total articles extracted: {count}")

with open("abstracts.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Done! Saved to abstracts.json")