#!/usr/bin/env python3

from graph_tool.all import *
from urllib.parse import urlparse

import os
import re
import requests

guid_pattern = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)


class CfApi(object):
    root_path = '/v3'

    def __init__(self, api, token):
        self.api = api
        self.token = token

    def get(self, endpoint):
        headers = {'Authorization': self.token}
        url = f'http://{self.api}{endpoint}'
        r = requests.get(url, headers=headers)
        return r.json()

class Link(object):
    def __init__(self, linkDict):
        self.href = linkDict.get('href')
        self.method = linkDict.get('method')
        self.path = urlparse(self.href).path

    def is_read(self):
        return self.method in ['GET', None]

    def is_v3(self):
        return 'v3' in self.href

    def is_download(self):
        return 'download' in self.href


class ResourcePath(object):
    guid_placeholder = ':guid'
    type_placeholder = ':type'
    placeholders = [guid_placeholder, type_placeholder]

    def __init__(self, path):
        self.path = path

    def generic_path(self):
        sub_guids = guid_pattern.sub(self.__class__.guid_placeholder, self.path)
        return sub_guids.replace('web', self.__class__.type_placeholder)

    def infer_resource(self):
        segments = self.generic_path().split('/')
        non_guid_segments = [segment for segment in segments if segment not in self.__class__.placeholders]
        return non_guid_segments[-1]

class ResourceGraph(object):
    v3_color = '#1C366B'
    v2_color = '#1DACE8'

    def __init__(self):
        self.graph = Graph()

        self.v_names = self.graph.new_vertex_property("string")
        self.v_colors = self.graph.new_vertex_property("string")
        self.e_names = self.graph.new_edge_property("string")

        self.vertices = {}
        self.edges = {}

    def add_resource(self, resource_name, is_v3=True):
        vertex = self.graph.add_vertex()
        self.vertices[resource_name] = vertex
        self.v_names[vertex] = resource_name
        self.v_colors[vertex] = self.__class__.v3_color if is_v3 else self.__class__.v2_color

    def has_resource(self, resource_name):
        return resource_name in self.vertices

    def add_link(self, source_name, destination_name, name):
        source = self.vertices[source_name]
        destination = self.vertices[destination_name]

        edge = self.graph.add_edge(source, destination)
        edge_id = self.edge_id(source_name, destination_name, name)
        self.edges[edge_id] = edge
        self.e_names[edge] = name

    def has_link(self, source_name, destination_name, name):
        return self.edge_id(source_name, destination_name, name) in self.edges

    def edge_id(self, source_name, destination_name, name):
        return f'{name} -- {source_name} -- {destination_name}'

    def draw(self):
        graph_draw(
                self.graph,
                pos=radial_tree_layout(self.graph, self.graph.vertex(0)),
                vertex_text=self.v_names,
                vertex_fill_color=self.v_colors,
                edge_text=self.e_names,
                output_size=(2000,1300),
                fit_view=True,
                vertex_font_size=10,
                vertex_pen_width=1,
                vertex_halo=False,
                edge_pen_width=3,
                )

class Crawler(object):
    def __init__(self, cf_api, graph):
        self.cf_api = cf_api
        self.visited_paths = set()
        self.graph = graph

    def find_all_paths(self, root):
        root_resource = ResourcePath(root)
        root_sans_guid = root_resource.generic_path()
        resource_name = root_resource.infer_resource()

        print(f'{root_sans_guid} -- {resource_name}')

        self.visited_paths.add(root_sans_guid)

        if not self.graph.has_resource(resource_name):
            self.graph.add_resource(resource_name)

        for link in self.get_links_from_endpoint(root):
            path = link.path
            linked_resource = ResourcePath(path)
            path_sans_guid = linked_resource.generic_path()
            linked_resource_name = linked_resource.infer_resource()

            print(f'    {path_sans_guid} -- {linked_resource_name}')

            if not self.graph.has_resource(linked_resource_name):
                self.graph.add_resource(linked_resource_name, link.is_v3())

            if not self.graph.has_link(resource_name, linked_resource_name, path_sans_guid):
                self.graph.add_link(resource_name, linked_resource_name, path_sans_guid)

            if link.is_read() and link.is_v3() and not link.is_download() and path_sans_guid not in self.visited_paths:
                self.find_all_paths(path)

    def get_links_from_endpoint(self, endpoint):
        response = self.cf_api.get(endpoint)
        response_links = response.get('links') or response.get('resources')[-1].get('links')
        if response_links:
            link_dicts = response_links.values()
            return [Link(link) for link in link_dicts]
        else:
            print(f'{endpoint} has no links')
            return []


def main():
    api = os.environ['CF_API']
    token = os.environ['CF_TOKEN']
    cfapi = CfApi(api, token)
    graph = ResourceGraph()
    crawler = Crawler(cfapi, graph)
    crawler.find_all_paths(CfApi.root_path)
    print(crawler.visited_paths)
    graph.draw()


if __name__ == "__main__":
    main()
