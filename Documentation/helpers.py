"""Helper functions for generating PMO RDF and HTML"""

import datetime
import pathlib
import urllib.parse
import xml.etree.ElementTree as etree

import rdflib

from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(['html', 'xml'])
)

DC = rdflib.Namespace("http://purl.org/dc/terms/")
OWL = rdflib.Namespace("http://www.w3.org/2002/07/owl#")
RDACT = rdflib.Namespace("http://rdaregistry.info/termList/RDACarrierType/")
SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")

LOOKUPS = {
    "http://id.loc.gov/ontologies/bibframe/Contribution": "contribution",
    "http://id.loc.gov/ontologies/bibframe/derivativeOf": "derivative of",
    "http://id.loc.gov/ontologies/bibframe/date": "Date",
    "http://id.loc.gov/ontologies/bibframe/Event": "event",
    "http://id.loc.gov/ontologies/bibframe/eventContent": "event content",
    "http://id.loc.gov/ontologies/bibframe/eventContentOf": "event content of",
    "http://id.loc.gov/ontologies/bibframe/hasDerivative": "has derivative",
    "http://id.loc.gov/ontologies/bibframe/Identifier": "identifier",
    "http://id.loc.gov/ontologies/bibframe/Organization": "organization",
    "http://id.loc.gov/ontologies/bibframe/referencedBy": "referenced by",
    "http://id.loc.gov/ontologies/bibframe/references": "references",
    "http://id.loc.gov/ontologies/bibframe/relatedTo": "related to",
    "http://id.loc.gov/ontologies/bibframe/Work": "work"
}

def _add_superclasses(subject_uri: str, pmo_graph: rdflib.Graph) -> list:
    subj = rdflib.URIRef(subject_uri)
    super_classes = []
    sub_class_of = pmo_graph.objects(subject=subj, predicate=rdflib.RDFS.subClassOf)
    if sub_class_of:
        for super_class in sub_class_of:
            label = _check_for_label(super_class, pmo_graph)
            if not label:
                raise ValueError(f"{subj} super-class {super_class} doesn't have a label")
            output = {
                "uri": str(super_class),
                "label": label
            }
            super_classes.append(output)
    return super_classes


def _build_info(subj: rdflib.URIRef, pmo_graph: rdflib.Graph) -> dict:
    class_info = {
        "id": str(subj).split("/")[-1],
        "uri": str(subj),
    }
    label = pmo_graph.value(subject=subj, predicate=rdflib.RDFS.label)
    if label:
        class_info["label"] = str(label)
    else:
        class_info["label"] = class_info["id"]
    definition = pmo_graph.value(subject=subj, predicate=SKOS.definition)
    if definition:
        class_info["definition"] = str(definition)
    examples = pmo_graph.objects(subject=subj, predicate=SKOS.example)
    if examples:
        class_info["example"] = [str(i) for i in examples]
    return class_info


def _change_note(uri: rdflib.URIRef, graph: rdflib.Graph) -> str:
    """Get the change note for a given URI."""
    change_note_bnode = graph.value(subject=uri, predicate=SKOS.changeNote)
    note_val = graph.value(subject=change_note_bnode, predicate=rdflib.RDF.value)
    date = graph.value(subject=change_note_bnode, predicate=DC.date)
    return f"{note_val} {date}"


def _check_for_label(object_, graph: rdflib.Graph) -> str:
    label = None
    if str(object_) in LOOKUPS:
        label = LOOKUPS[str(object_)]
    if not label:
        label = graph.value(subject=object_, predicate=rdflib.RDFS.label)
        if label:
            label = str(label)
    if label and str(object_).startswith("http://performedmusicontology.org"):
        label = _create_link_super(object_, label)
    return label


def _create_link_super(object_, label):
    ident = str(object_).split("/")[-1]
    return f"""<a href="#{ident}" title="{object_}">{label}</a>
    <sup title="object property" class="type-op">op</sup>"""


def _generate_description(subject: rdflib.URIRef, graph: rdflib.Graph, all_obj_props: dict) -> dict:
    object_prop_description = { 
        "super_properties": [],
        "domain": [],
        "range": [],
        "inverse_of": [],
        "has_description": False,
    }
    for obj in graph.objects(subject=subject, predicate=rdflib.RDFS.subPropertyOf):
        label = _check_for_label(obj, graph)
        if not label:
            raise ValueError(f"{subject}'s {obj} super properties not found in lookups")
        object_prop_description["has_description"] = True
        object_prop_description["super_properties"].append(
            {
                "uri": str(obj),
                "label": label
            }
        )
    for obj in graph.objects(subject=subject, predicate=rdflib.RDFS.domain):
        label = _check_for_label(obj, graph)
        if not label:
            raise ValueError(f"{subject}'s domain of {obj} not found")
        object_prop_description["has_description"] = True
        object_prop_description["domain"].append(
            {
                "uri": str(obj),
                "label": label
            }
        )
    for obj in graph.objects(subject=subject, predicate=rdflib.RDFS.range):
        label = _check_for_label(obj, graph)
        if not label:
            raise ValueError(f"{subject}'s range of {obj} not found")
        object_prop_description["has_description"] = True
        object_prop_description["range"].append(
            {
                "uri": str(obj),
                "label": label,
            }
        )
    for obj in graph.objects(subject=subject, predicate=OWL.inverseOf):
        label = _check_for_label(obj, graph)
        if not label:
            raise ValueError(f"{subject} inverseOf {obj} not found")
        object_prop_description["has_description"] = True
        object_prop_description["inverse_of"].append(
            {
                "uri": str(obj),
                "label": label
            }
        )
    return object_prop_description


def generate_data_properties(pmo_graph: rdflib.Graph, pmo_html_path: pathlib.Path) -> dict:
    data_types = {}
    print("Generating data properties")
    for subject in pmo_graph.subjects(predicate=rdflib.RDF.type, object=OWL.DatatypeProperty):
        init_entity(
            entity=subject,
            ontology_path=pmo_html_path.parent,
            ontology_graph=pmo_graph,
            html_doc_file="/ontology/PMO.html"
        )
        subject_uri = str(subject)
        ident = subject_uri.split("/")[-1]
        data_type = {
            "id": ident,
            "uri": subject_uri
        }
        label = pmo_graph.value(subject=subject, predicate=rdflib.RDFS.label)
        if label:
            data_type["label"] = str(label)
        else:
            data_type["label"] = ident
        data_type.update(_generate_description(subject, pmo_graph, data_types))
        definition = pmo_graph.objects(subject=subject, predicate=SKOS.definition)
        if definition:
            data_type["definition"] = [str(s) for s in definition]
        comments = pmo_graph.objects(subject=subject, predicate=rdflib.RDFS.comment)
        if comments:
            data_type["comments"] = [str(s) for s in comments]
        data_types[subject_uri] = data_type
        print(f"\tFinished data property {ident}")
    return data_types


def generate_object_properties(pmo_graph: rdflib.Graph, pmo_html_path: pathlib.Path) -> dict:
    object_properties = [s for s in pmo_graph.subjects(predicate=rdflib.RDF.type, object=OWL.ObjectProperty)]
    print(f"Generating Object {len(object_properties)} Properties")
    objects_props = {}
    for subj in object_properties:
        init_entity(
            entity=subj,
            ontology_path=pmo_html_path.parent,
            ontology_graph=pmo_graph,
            html_doc_file="/ontology/PMO.html"
        )
        object_property = {
            "id": str(subj).split("/")[-1],
            "uri": str(subj)
        }
        object_property.update(_generate_description(subj, pmo_graph, objects_props))
        objects_props[str(subj)] = object_property
        label = pmo_graph.value(subject=subj, predicate=rdflib.RDFS.label)
        if not label:
            object_property["label"] = str(subj).split("/")[-1]
        else:
            object_property["label"] = str(label)
        definition = [str(s) for s in pmo_graph.objects(subject=subj, predicate=SKOS.definition)]
        if len(definition) > 0:
            object_property["definition"] = definition
        print(f"\tFinished object property {object_property['id']}")
    return objects_props


def generate_pmo_classes(pmo_graph: rdflib.Graph, pmo_html_path: pathlib.Path) -> dict:
    pmo_classes = [subj for subj in pmo_graph.subjects(predicate=rdflib.RDF.type, object=OWL.Class)]
    print(f"Generating {len(pmo_classes)} PMO classes")
    classes = {}
    for subject in pmo_classes:
        init_entity(
            entity=subject,
            ontology_path=pmo_html_path.parent,
            ontology_graph=pmo_graph,
            html_doc_file="/ontology/PMO.html"
        )
        subject_key = str(subject)
        classes[subject_key] = _build_info(subject, pmo_graph)
        super_classes = _add_superclasses(subject_key, pmo_graph)
        if len(super_classes) > 0:
            classes[subject_key]["superClass"] = super_classes
        print(f"\tFinished PMO class {subject}")
    return classes


def generate_vocab_home(**kwargs):
    """Generate the vocabulary home page and RDF files."""

    ontology_entity: rdflib.URIRef = kwargs["ontology_entity"]
    graph: rdflib.Graph = kwargs["graph"]
    pmo_base_path: pathlib.Path = kwargs["pmo_base_path"]
    ontology_path: pathlib.Path = kwargs["ontology_path"]
    html_doc_file: str = kwargs["html_doc_file"]
    entities: list = kwargs["entities"]
    main_html_template = env.get_template("ontology_home.html")

    vocab = {
        "title": graph.value(subject=ontology_entity, predicate=DC.title),
        "url": str(ontology_entity),
        "definition":  graph.value(subject=ontology_entity, predicate=SKOS.definition)
    }
    classes = []
    for entity in entities:
        class_ = {
            "id": str(entity).split("/")[-1],
            "definition": graph.value(subject=entity, predicate=SKOS.definition),
            "prefLabel":  graph.value(subject=entity, predicate=SKOS.prefLabel),
            "changeNote": _change_note(entity, graph),
            "url": str(entity)
        
        }
        alt_label = graph.value(subject=entity, predicate=SKOS.altLabel)
        if alt_label:
            class_["altLabel"] = alt_label
        classes.append(class_)
    vocab_home_path = ontology_path / f"{html_doc_file}.html"
    with vocab_home_path.open("w+") as fo:
        fo.write(main_html_template.render(vocab=vocab, classes=classes))
    rdf_vocab_home_path = ontology_path / f"{html_doc_file}.rdf"
    with rdf_vocab_home_path.open("w+") as fo:
        fo.write(graph.serialize(format='xml'))
    ttl_vocab_home_path = ontology_path / f"{html_doc_file}.ttl"
    with ttl_vocab_home_path.open("w+") as fo:
        fo.write(graph.serialize(format='turtle'))


def init_entity(**kwargs):
    entity = kwargs.get('entity')
    ontology_path = kwargs.get("ontology_path")
    ontology_graph = kwargs.get("ontology_graph")
    html_doc_file = kwargs.get("html_doc_file")

    entity_parts = str(entity).split("http://performedmusicontology.org/")[-1].split("/")
    name = entity_parts[-1]
    page_path = "/".join(entity_parts)
 
    html_template  = env.get_template("page.html")

    # Make sub-directory if it doesn't exist
    entity_path = ontology_path / name
    if not entity_path.exists():
        entity_path.mkdir(parents=True, exist_ok=True)
    # Create an HTML file that redirects to Entity
    html_path = entity_path / "index.html"
    label = ontology_graph.value(subject=entity, predicate=SKOS.prefLabel)
    if label is None:
        label = name
  
    with html_path.open("w+") as fo:
        fo.write(html_template.render(doc_home=html_doc_file,
                                      page_path=f"/{page_path}",
                                      label=label, 
                                      name=name))

    graph = rdflib.ConjunctiveGraph()
    graph.namespace_manager.bind("dc", DC)
    graph.namespace_manager.bind("rdact", RDACT)
    graph.namespace_manager.bind("skos", SKOS)
    for pred, obj in ontology_graph.predicate_objects(entity):
        graph.add((entity, pred, obj))
        if isinstance(obj, rdflib.BNode):
            for bnode_pred, bnode_obj in ontology_graph.predicate_objects(obj):
                graph.add((obj, bnode_pred, bnode_obj))
    # Writes an RDF XML file
    rdf_xml_path = entity_path / f"{name}.rdf"
    save_rdf(graph, rdf_xml_path, "xml")
    # Writes a RDF Turtle file
    rdf_ttl_path = entity_path / f"{name}.ttl"
    save_rdf(graph, rdf_ttl_path, "ttl") 
    print("{time} Finished initializing {label}".format(
          **{ "time": datetime.datetime.now(datetime.UTC).isoformat(),
            "label": label }))
    
    return f"""<li><a href="{entity}">{label}</li>"""
    

def init_vocabulary(**kwargs):
    """Initialize the vocabulary by generating HTML and RDF files."""
    pmo_base_path = kwargs.get("pmo_base_path")
    rdf_file = kwargs.get("rdf_file")
    html_doc_file = kwargs.get("html_doc_file")
    ontology_html_template = env.get_template("ontology_home.html")

    rdf_path = pmo_base_path / rdf_file
    start = datetime.datetime.now(datetime.UTC)
    print("{} Staring ontology initialization".format(start.isoformat()))
    if not rdf_path.exists():
        raise ValueError(f"{rdf_path} rdf_path doesn't exist")
    ontology_graph = rdflib.Graph()
    ontology_graph.parse(rdf_path, format='turtle')
    ontology_entity = ontology_graph.value(predicate=rdflib.RDF.type, object=SKOS.ConceptScheme)
    ontology_label = ontology_graph.value(subject=ontology_entity, predicate=rdflib.RDFS.label)
    entities = list(ontology_graph.subjects(predicate=rdflib.RDF.type, object=SKOS.Concept))
    ontology_uri = urllib.parse.urlparse(str(ontology_entity))
    ontology_path = pmo_base_path / ontology_uri.path[1:]
    print(ontology_path.absolute(), ontology_path.exists())
    if not ontology_path.exists():
        ontology_path.mkdir(parents=True, exist_ok=True)
    generate_vocab_home(
        ontology_entity=ontology_entity,
        graph=ontology_graph,
        pmo_base_path=pmo_base_path,
        ontology_path=ontology_path,
        vocab_name=ontology_label,
        html_doc_file=html_doc_file,
        entities=entities)
    entity_list_html = ''
    for row in entities:
        entity_list_html += "{}\n".format(
            init_entity(entity=row,
                        ontology_path=ontology_path,
                        ontology_graph=ontology_graph,
                        html_doc_file=f"{html_doc_file}.html")
            )
    vocab_home_template = env.get_template("vocab_home.html")

    raw_html = vocab_home_template.render(
            label=ontology_label,
            html_doc_file=html_doc_file,
            entities_list=entity_list_html)
    with (ontology_path / "index.html").open("w+") as fo:
        fo.write(raw_html)
    end = datetime.datetime.now(datetime.UTC)
    print(f"\n{end.isoformat()} - Finished {ontology_label}, total time {(end-start).seconds / 60.0:,} minutes")


def pmo_homepage(pmo_rdf_path: pathlib.Path, pmo_html_path: pathlib.Path):
    print("Starting PMO HTML generation")
    pmo_graph = rdflib.Graph()
    pmo_graph.parse(data=pmo_rdf_path.read_text(), format="xml")
    pmo_home_template = env.get_template("pmo_home.html")
    pmo_classes = generate_pmo_classes(pmo_graph, pmo_html_path)
    print(f"Total PMO classes {len(pmo_classes)}")
    object_properties = generate_object_properties(pmo_graph, pmo_html_path)
    print(f"Total PMO object properties {len(object_properties)}")
    data_properties = generate_data_properties(pmo_graph, pmo_html_path)
    print(f"Total PMO data properties {len(data_properties.values())}")

    rendered_pmo_html = pmo_home_template.render(
        classes = pmo_classes.values(),
        object_properties = object_properties.values(),
        data_types= data_properties.values()
    )
    with pmo_html_path.open("w+") as fo:
        fo.write(rendered_pmo_html)
    print("Finished generating PMO HTML")


def save_rdf(graph, path, serialize_as):
    # print("{} Saving {}, {} triples as {}".format(datetime.datetime.now(datetime.UTC).isoformat(),
    #                                           path,
    #                                           len(graph),
    #                                           serialize_as))
    #path.mkdir(parents=True, exist_ok=True)
    with path.open("w+") as fo:
        fo.write(graph.serialize(format=serialize_as))