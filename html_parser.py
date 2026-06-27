from bs4 import BeautifulSoup
import bs4
import json
from playwright.sync_api import sync_playwright
import re
import requests



class HTMLParser:

    def __init__(self, src : str, is_link=False):
        self.source_name = src
        possible_name_patterns = [r"(?<=(https://))[\w_-]+", r"(?<=(http://))[\w_-]+"]
        self.ignore = ( "svg",
                        "path",
                        "rect",
                        "circle",
                        "line",
                        "polygon",
                        "polyline",
                        "ellipse",
                        "script", 
                        "style", )
        if is_link:
            found_name = False
            i = 0
            while (not found_name):
                if (i + 1 == len(possible_name_patterns)):
                    break
                try:
                    self.source_name = re.search(possible_name_patterns[i], src).group(0)
                    found_name = True
                    break
                except(AttributeError):
                    i += 1

            if (not found_name):
                self.source_name = "parsed_website_no_name"
                found_name = True
                
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
        root = self.parser.find("html")
        if (root == None):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(src)
                page.wait_for_timeout(3000)

                html = page.content()
                browser.close()
        self.parser = BeautifulSoup(html, "html.parser")
        root = self.parser.find("html")
        if (root == None):
            raise ValueError("something went wrong")
        self.load_in_descendants(root)
        self.export()


    def get_plain_text(self, tag : bs4.element.Tag, output_sep = "\n", sep=" ", strip_=True) -> str:
        
        plain_text_string = ""
        #plain_text_string += tag.get_text(separator=sep, strip=strip_) + output_sep
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

    def __getitem__(self, key : str) -> None:
        if (key in self.components.keys()):
            return self.components[key]
        return None

    

    def generate_key(self, tag : bs4.element.Tag) -> str:
        """
        generates key for param: tag
        """

        class_found = False
        id_found = False

        if (not tag.parent):
            return tag.name

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
                    parent_part += "#" + "".join(container_ids)
        except (AttributeError):
            pass

        if (tag_part == None):
            key = parent_part
        elif (parent_part == None):
            key = tag_part
        else:
            key = parent_part + " > " + tag_part

        return key

    def load_in_direct_children(self, tag : bs4.element.Tag) -> None:
        '''
        param tag: bs4.element.Tag root tag to start from
        
        puts direct children of root into dictionary into HTMLParser.components
        '''
        tag_direct_children_dictionary = {}
        key = self.generate_key(tag)

        children = tag.children

        for child in children:
            if (child.name in self.ignore):
                continue
            if (not isinstance(child, bs4.element.Tag)):
                continue
            self.load_in_a_tag(child, tag_direct_children_dictionary)
        self.components[key + " DIRECT CHILDREN"] = tag_direct_children_dictionary
        return


    def load_in_descendants(self, tag : bs4.element.Tag) -> None:
        '''
        param tag: bs4.element.Tag root tag to start from
        
        puts all descendants of root into dictionary into HTMLParser.components
        '''
        if (tag == None):
            return
        tag_hierarchy_dictionary = {}
        key = self.generate_key(tag)
        
        descendants = tag.descendants
        
        for child in descendants:
            if (child.name in self.ignore):
                continue
            if (not isinstance(child, bs4.element.Tag)):
                continue
            self.load_in_a_tag(child, tag_hierarchy_dictionary)
        self.components[key + " DESCENDANTS"] = tag_hierarchy_dictionary
        return

    def generate_css_selectors(self, tag : bs4.element.Tag) -> list:
        css_selectors = [tag.name + "." + f"{'.'.join(tag.get('class'))}" if tag.get("class") else "", 
                         tag.name + "#" + f"{''.join(tag.get('id'))}" if tag.get("id") else "",
                         tag.parent.name + "." + f"{'.'.join(tag.parent.get('class'))}" + " > " + tag.name + "." + f"{'.'.join(tag.get('class'))}" if (tag.parent.get("class") and tag.get('class')) else "",
                         tag.parent.name + "." + f"{'.'.join(tag.parent.get('class'))}" + " > " + tag.name + "#" + f"{''.join(tag.get('id'))}" if (tag.parent.get("class") and tag.get('id')) else "",
                         tag.parent.name + "#" + f"{''.join(tag.parent.get('id'))}" + " > " + tag.name + "." + f"{'.'.join(tag.get('class'))}" if (tag.parent.get("id") and tag.get('class')) else "",
                         tag.parent.name + "#" + f"{''.join(tag.parent.get('id'))}" + " > " + tag.name + "#" + f"{''.join(tag.get('id'))}" if (tag.parent.get("id") and tag.get('id')) else ""]

        while ("" in css_selectors):
            css_selectors.remove("")

        return css_selectors

        

    def load_in_a_tag(self, tag : bs4.element.Tag, container : dict) -> None:
        #tag = self.parser.find(tag_name)
            
        key = self.generate_key(tag)
        container[key] = {"parent": tag.parent.name,
                          #"raw": tag,
                          "tag": tag.name,
                          "attributes": tag.attrs,
                          "plain text":self.get_plain_text(tag),
                          "css selectors":self.generate_css_selectors(tag)}
        #print(container)
        return

    def export(self):
        with open(f"{self.source_name}.json", "w") as file:
            json.dump(self.components, file, indent=4)
        file.close()


#parser = HTMLParser(src="https://www.irishstatutebook.ie/eli/2018/act/25/enacted/en/print.html", is_link=True)
#par = HTMLParser(src="website.html")#69a5b7a1baae6f0d37c19fe8.html
#parser.load_in_a_tag("h1")
#print(parser.components)
#parser["h1"] = parser.find_tag("h1")
#HTMLParser(src="69a5b7a1baae6f0d37c19fe8.html")
HTMLParser(src="https://avery-woodlief.dev/portfolio-page/portfolio.html", is_link=True)
#print(par.get_plain_text(tag))
#print(parser.get_plain_text(list(parser.components.keys())[0]))
#parser.load_in_descendants("script")
#print(parser.get_plain_text("div"))
#print(parser.components.keys())
#key=list(parser.components.keys())[0]
#print(parser[key].prettify())
#print(parser.get_plain_text("h1"))
#print(parser.find_tag("h1").prettify())
#print(parser.components)
