from bs4 import BeautifulSoup
import bs4
import json
from playwright.sync_api import sync_playwright
import re
import requests
from urllib.parse import urlparse




class HTMLParser:
    '''
    Good for single page parsing
    '''

    def __init__(   self, src : str,
                    tags_ignored=("svg","path","rect","circle","line","polygon","polyline","ellipse","script","style","img", "i", "div", "span", "td", "tr"),
                    classes_ignored=tuple(), 
                    ids_ignored=tuple(), 
                    only_look_for_tags=tuple(), 
                    only_look_for_classes=tuple(), 
                    only_look_for_ids=tuple()):

        self.source_name = src
        """
        possible_name_patterns = [  
                                    r"(?<=(https://www.))[\w_-]+",
                                    r"(?<=(http://www.))[\w_-]+",
                                    r"(?<=(https://))[\w_-]+",
                                    r"(?<=(http://))[\w_-]+"
                                 ]
        """
        self.ignore_tags = tags_ignored
        self.ignore_classes = classes_ignored
        self.ignore_ids = ids_ignored
        self.selective_tags = only_look_for_tags
        self.selective_classes = only_look_for_classes
        self.selective_ids = only_look_for_ids
        is_link = False
        result = urlparse(src)
        if (result.scheme in ("https", "http")):
            is_link = True
            self.source_name = result.netloc
            if (re.search(r"(?<=[.])\w+(?=[.])", self.source_name)):
                self.source_name = re.search(r"(?<=[.])\w+(?=[.])", self.source_name).group(0)
            else:
                self.source_name = "no_name_site"
        if is_link:
                
            self.source = requests.get(src).text
        else:
            with open(src, "r") as file:
                self.source = file.read()
        self.parser = BeautifulSoup(self.source, "html.parser")
        self.components = {}
        """
        === self.components ===
        keys: [parent tag].tag-[all class names]-[all id names] OR
              [parent tag]-[container class names].tag-[all id names] if tag has no class, but has ids
              [parent tag]-[container id names].tag-[all class names] if tag has no id, but has class
              [parent tag]-[container class names]-[container id names].tag if tag has neither class nor id
        ___________________________________________________________________________________________________________
                    NOTE: container may not equal parent tag
                          it is first wrapping container that has what is lacking, either class or id names or both
                    NOTE: the group of class names is prefix by a -[c], the id group is prefixed by a -[i]
        ___________________________________________________________________________________________________________

        values: objects of type bs4.element.Tag
        
        """
        html = self.parser.find("html")
        body = self.parser.find("body")
        if (html == None):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(src)
                page.wait_for_timeout(3000)

                html_ = page.content()
                self.parser = BeautifulSoup(html_, "html.parser")
                browser.close()
                html = self.parser.find("html")
                body = self.parser.find("body")
                if (html == None):
                    raise ValueError("something went wrong")
        self.html = html
        self.body = body
        self.root = self.parser
        
    def standard_parse(self):
        self.load_in_descendants(self.body, False)
        self.export()

    def selective_parse(self):
        self.load_in_descendants(self.body, True)
        self.export()

    def is_ignored(self, tag : bs4.element.Tag) -> bool:
        if (not isinstance(tag, bs4.element.Tag)):
            return False
        if (tag.name in self.ignore_tags):
            return True
        if (tag.get("class")):
            for class_ in tag.get("class"):
                if class_ in self.ignore_classes:
                    return True
        if (tag.get("id")):
            for id_ in tag.get("id"):
                if id_ in self.ignore_ids:
                    return True
        return False

    def passes_selection(self, tag : bs4.element.Tag) -> bool:
        if (not isinstance(tag, bs4.element.Tag)):
            return True

        passed_name = False
        passed_class_ = False
        passed_id_ = False
        
        if (len(self.selective_tags) > 0):
            for selective_tag in self.selective_tags:
                if (re.fullmatch(rf"{selective_tag}", tag.name)):
                    passed_name = True
                    break
        else:
            passed_name = True
        if (tag.get("class") and (len(self.selective_classes) > 0)):
            for class_ in tag.get("class"):
                if (class_ in self.selective_classes):
                    passed_class_ = True
                    break
        elif (len(self.selective_classes) == 0):
            passed_class_ = True
        if (tag.get("id") and (len(self.selective_ids) > 0)):
            for id_ in tag.get("id"):
                if (id_ in self.selective_ids):
                    passed_id_ = True
                    break
        elif (len(self.selective_ids) == 0):
            passed_id_ = True
        return (passed_name and passed_class_ and passed_id_)


    def get_plain_text(self, tag : bs4.element.Tag, output_sep = "\n", sep=" ", strip_=True) -> str:
        
        plain_text_string = ""
        text_in_list = tag.get_text().strip(" \t\n").split("\n")
        plain_text_string += text_in_list[0].strip(" \t\n")
        for line in text_in_list:
            if line == text_in_list[0]:
                continue
            plain_text_string += ", " + line.strip(" \t\n")

        return plain_text_string

    def find_container_class(self, tag):
        parent = tag.parent

        while parent and parent.name != "[document]":
            if parent.get("class"):
                return parent["class"]

            parent = parent.parent

        return None

    def find_container_id(self, tag):
        parent = tag.parent

        while parent and parent.name != "[document]":
            if parent.get("id"):
                
                return parent["id"]

            parent = parent.parent

        return None

    def find_tag_from_classes(self, classes : list) -> bs4.element.Tag:
        for tag in self.root.find_all():
            if (self.is_ignored(tag)):
                continue
            if (tag.get("class") == classes):
                return tag
        return None

    def find_tag_from_id(self, ids : list) -> bs4.element.Tag:
        for tag in self.root.find_all():
            if (self.is_ignored(tag)):
                continue
            if (tag.get("id") == ids):
                return tag
        return None

    def __getitem__(self, key : str) -> None:
        if (key in self.components.keys()):
            return self.components[key]
        return None

    

    def generate_key(self, tag : bs4.element.Tag, container : dict) -> str:
        """
        generates key for param: tag
        param: container is used to check if generated key already exists
        part of the key generated is a valid css selector for the given tag
        the other part of the generated key is to prevent overwriting other keys with the same classname/id under the same parent and same tag 
                                                                                 or under same first elder with same classname/id and same tag.
        """

        class_found = False
        id_found = False

        if (not tag.parent):
            return tag.name

        direct_child = True

        parent_part = tag.parent.name
        tag_part = tag.name
        

        try:
            if (tag.get("class")):
                class_found = True
                classes = tag.get("class")
                tag_part += "." + ".".join(classes)
            else:
                container_classes = self.find_container_class(tag)
                if (container_classes):
                    #parent_part = p.name
                    elder = self.find_tag_from_classes(container_classes)
                    if (tag.parent.name != elder.name):
                        direct_child = False
                        parent_part = elder.name
                    
                    parent_part += "." + ".".join(container_classes)
        except (AttributeError):
            pass
            
        try:
            if (tag.get("id")):
                id_found = True
                ids = tag.get("id")
                tag_part += "#" + "".join(ids)
            else:
                container_ids = self.find_container_id(tag)
                if (container_ids):
                    #parent_part = p.name
                    elder = self.find_tag_from_id(container_ids)
                    if (elder.name != tag.parent.name):
                        direct_child = False
                        parent_part = elder.name
                    parent_part += "#" + "".join(container_ids)
        except (AttributeError):
            pass

        if (tag_part == None):
            key = parent_part
        elif (parent_part == None):
            key = tag_part
        else:
            if (direct_child):
                key = parent_part + " > " + tag_part
            else:
                key = parent_part + " " + tag_part

        if key in container.keys():
            addr = re.search(r"(?<=0x)[\w]+(?=[>])", str(key.__hash__)).group(0) # uses memory address as attempt to make key unique
            key += f"%{addr}"

        return key

    def load_in_direct_children(self, tag : bs4.element.Tag, selective : bool) -> None:
        '''
        param tag: bs4.element.Tag root tag to start from
        
        puts direct children of root into dictionary into HTMLParser.components
        '''
        tag_direct_children_dictionary = {}
        key = self.generate_key(tag, tag_direct_children_dictionary)

        children = tag.children

        for child in children:
            if (not selective):
                if (self.is_ignored(child)):
                    continue
            else:
                if (not self.passes_selection(child)):
                    continue
            self.load_in_a_tag(child, tag_direct_children_dictionary)
        self.components[key + " DIRECT CHILDREN"] = tag_direct_children_dictionary
        return


    def load_in_descendants(self, tag : bs4.element.Tag, selective : bool) -> None:
        '''
        param tag: bs4.element.Tag root tag to start from
        
        puts all descendants of root into dictionary into HTMLParser.components
        '''
        if (tag == None):
            return
        tag_hierarchy_dictionary = {}
        key = self.generate_key(tag, tag_hierarchy_dictionary)
        
        descendants = tag.descendants
        
        for child in descendants:
            if (not selective):
                if (self.is_ignored(child)):
                    continue
            else:
                if (not self.passes_selection(child)):
                    continue
            if (not isinstance(child, bs4.element.Tag)):
                continue
            self.load_in_a_tag(child, tag_hierarchy_dictionary)
        self.components[key + " DESCENDANTS"] = tag_hierarchy_dictionary
        return

    def generate_css_selectors(self, tag : bs4.element.Tag, container : list) -> list:
        key = self.generate_key(tag, container)
        css_selectors = [   
                            tag.name + "." + f"{'.'.join(tag.get('class'))}" if tag.get("class") else "", 
                            tag.name + "#" + f"{''.join(tag.get('id'))}" if tag.get("id") else "",
                            tag.parent.name + "." + f"{'.'.join(tag.parent.get('class'))}" + " > " + tag.name + "." + f"{'.'.join(tag.get('class'))}" if (tag.parent.get("class") and tag.get('class')) else "",
                            tag.parent.name + "." + f"{'.'.join(tag.parent.get('class'))}" + " > " + tag.name + "#" + f"{''.join(tag.get('id'))}" if (tag.parent.get("class") and tag.get('id')) else "",
                            tag.parent.name + "#" + f"{''.join(tag.parent.get('id'))}" + " > " + tag.name + "." + f"{'.'.join(tag.get('class'))}" if (tag.parent.get("id") and tag.get('class')) else "",
                            tag.parent.name + "#" + f"{''.join(tag.parent.get('id'))}" + " > " + tag.name + "#" + f"{''.join(tag.get('id'))}" if (tag.parent.get("id") and tag.get('id')) else "",
                            key[:key.index("%")] if ("%" in key) else key
                        ]

        while ("" in css_selectors):
            css_selectors.remove("")

        return css_selectors

        

    def load_in_a_tag(self, tag : bs4.element.Tag, container : dict) -> None:
        #tag = self.parser.find(tag_name)
            
        key = self.generate_key(tag, container)
        container[key] = {"parent": tag.parent.name,
                          #"raw": tag,
                          "tag": tag.name,
                          "attributes": tag.attrs,
                          "plain text":self.get_plain_text(tag),
                          "css selectors":self.generate_css_selectors(tag, container)}
        #print(container)
        return

    def export(self):
        with open(f"{self.source_name}.json", "w") as file:
            json.dump(self.components, file, indent=4)
        file.close()





# example usage

"""
source=input("")
if re.search(r"https|http", source):
    parser=HTMLParser(src=source, only_look_for_classes=("act-content", "smallcaps"))
    parser.selective_parse()
else:
    HTMLParser(src=source, tags_ignored=("svg","path","rect","circle","line","polygon","polyline","ellipse","script","style","tr", "table", "hr", "b", "div", "p", "td", "a", "ol", "li", "ul", "header", "nav", "footer", "i", "img", "header", "search", "span", "input", "form", "section", "main", "option", "cite", "select", "label", "h1", "button"), classes_ignored=("smallcaps"))
"""
