import re
import sys
from collections import namedtuple
from itertools import filterfalse
from pathlib import Path
from typing import List

import rclpy
from ament_index_python import get_package_share_directory
from jinja2 import Environment, FileSystemLoader
from rcl_interfaces.srv import ListParameters
from ros2cli.node.direct import DirectNode
from ros2cli.node.strategy import NodeStrategy, add_arguments
from ros2node.api import (INFO_NONUNIQUE_WARNING_TEMPLATE, NodeNameCompleter,
                          TopicInfo, get_absolute_node_name,
                          get_action_client_info, get_action_server_info,
                          get_node_names, get_publisher_info,
                          get_service_client_info, get_service_server_info,
                          get_subscriber_info)
from ros2param.api import (call_describe_parameters, call_get_parameters,
                           get_value)

from ros2model.api import (fix_topic_names, fix_topic_types,
                           get_parameter_type_string)
from ros2model.verb import VerbExtension

ParamInfo = namedtuple("Topic", ("name", "types", "default"))

BlackList_Subscribers = [
    TopicInfo("/parameter_events", ["rcl_interfaces/msg/ParameterEvent"])
]
BlackList_Publishers = [
    TopicInfo("~/transition_event", ["lifecycle_msgs/msg/TransitionEvent"]),
    TopicInfo("/parameter_events", ["rcl_interfaces/msg/ParameterEvent"]),
    TopicInfo("/rosout", ["rcl_interfaces/msg/Log"]),
]
BlackList_ServiceServers = [
    TopicInfo("~/change_state", ["lifecycle_msgs/srv/ChangeState"]),
    TopicInfo("~/describe_parameters",
              ["rcl_interfaces/srv/DescribeParameters"]),
    TopicInfo("~/get_available_states",
              ["lifecycle_msgs/srv/GetAvailableStates"]),
    TopicInfo(
        "~/get_available_transitions", [
            "lifecycle_msgs/srv/GetAvailableTransitions"]
    ),
    TopicInfo("~/get_parameter_types",
              ["rcl_interfaces/srv/GetParameterTypes"]),
    TopicInfo("~/get_parameters", ["rcl_interfaces/srv/GetParameters"]),
    TopicInfo("~/get_state", ["lifecycle_msgs/srv/GetState"]),
    TopicInfo("~/get_transition_graph",
              ["lifecycle_msgs/srv/GetAvailableTransitions"]),
    TopicInfo("~/list_parameters", ["rcl_interfaces/srv/ListParameters"]),
    TopicInfo("~/set_parameters", ["rcl_interfaces/srv/SetParameters"]),
    TopicInfo(
        "~/set_parameters_atomically", [
            "rcl_interfaces/srv/SetParametersAtomically"]
    ),
]


def call_list_parameters(*, node, node_name, timeout=None):
    # create client
    client = node.create_client(ListParameters, f"{node_name}/list_parameters")

    # call as soon as ready
    ready = client.wait_for_service(timeout_sec=5.0)
    if not ready:
        raise RuntimeError("Wait for service timed out")

    request = ListParameters.Request()
    future = client.call_async(request)
    rclpy.spin_until_future_complete(
        node=node, future=future, timeout_sec=timeout)

    # handle response
    response = future.result()
    if response is None:
        try:
            e = future.exception()
        except:
            error = RuntimeError(
                f"Exception while calling service of node '{node_name}': {e}"
            )
        return response
    else:
        return response.result.names


class RunningNodeVerb(VerbExtension):
    """Dump information about a running node into a model."""

    def add_arguments(self, parser, cli_name):
        add_arguments(parser)
        group = parser.add_mutually_exclusive_group(required=True)

        argument = group.add_argument(
            "-n", "--node_name", help="Node name to request information"
        )
        argument.completer = NodeNameCompleter()

        group.add_argument(
            "-ga",
            "--generate-all",
            action="store_true",
            help="Generate models for all node in current running system",
        )

        parser.add_argument(
            "--include-hidden",
            action="store_true",
            help="Display hidden topics, services, and actions as well",
        )
        parser.add_argument(
            "-o",
            "--output",
            default=Path.cwd(),
            help="The output file for the generated model.",
        )

        parser.add_argument(
            "-dir",
            "--output-dir",
            default=".",
            help="The output file for the generated model.",
        )

        parser.add_argument(
            "-gv",
            "--generate-value",
            action="store_true",
            help="Wheather adding parameter value",
        )

    def create_a_node_model(self, target_node_name, output, if_param_value, args):
        subscribers: List[TopicInfo] = []
        publishers: List[TopicInfo] = []
        service_clients: List[TopicInfo] = []
        service_servers: List[TopicInfo] = []
        action_clients: List[TopicInfo] = []
        action_servers: List[TopicInfo] = []
        parameters: List[ParamInfo] = []

        with NodeStrategy(args) as node:
            node_name = get_absolute_node_name(target_node_name)
            node_names = get_node_names(
                node=node, include_hidden_nodes=args.include_hidden
            )
            count = [n.full_name for n in node_names].count(node_name)
            if count > 1:
                print(
                    INFO_NONUNIQUE_WARNING_TEMPLATE.format(
                        num_nodes=count, node_name=target_node_name
                    ),
                    file=sys.stderr,
                )
            if count > 0:
                print(target_node_name)
                subscribers = get_subscriber_info(
                    node=node,
                    remote_node_name=target_node_name,
                    include_hidden=args.include_hidden,
                )
                fix_topic_types(node_name, subscribers)
                subscribers = fix_topic_names(node_name, subscribers)
                subscribers = list(
                    filterfalse(
                        BlackList_Subscribers.__contains__, subscribers)
                )

                publishers = get_publisher_info(
                    node=node,
                    remote_node_name=target_node_name,
                    include_hidden=args.include_hidden,
                )
                fix_topic_types(node_name, publishers)
                publishers = fix_topic_names(node_name, publishers)
                publishers = list(
                    filterfalse(BlackList_Publishers.__contains__, publishers)
                )

                service_servers = get_service_server_info(
                    node=node,
                    remote_node_name=target_node_name,
                    include_hidden=args.include_hidden,
                )
                fix_topic_types(node_name, service_servers)
                service_servers = fix_topic_names(node_name, service_servers)
                service_servers = list(
                    filterfalse(
                        BlackList_ServiceServers.__contains__, service_servers)
                )

                service_clients = get_service_client_info(
                    node=node,
                    remote_node_name=target_node_name,
                    include_hidden=args.include_hidden,
                )
                fix_topic_types(node_name, service_clients)
                service_clients = fix_topic_names(node_name, service_clients)

                action_servers = get_action_server_info(
                    node=node,
                    remote_node_name=target_node_name,
                    include_hidden=args.include_hidden,
                )
                fix_topic_types(node_name, action_servers)
                action_servers = fix_topic_names(node_name, action_servers)

                action_clients = get_action_client_info(
                    node=node,
                    remote_node_name=target_node_name,
                    include_hidden=args.include_hidden,
                )
                fix_topic_types(node_name, action_clients)
                action_clients = fix_topic_names(node_name, action_clients)
            else:
                return "Unable to find node '" + target_node_name + "'"

        with DirectNode(args) as node:
            response = call_list_parameters(
                node=node, node_name=node_name, timeout=1.0)

            if response is not None:
                sorted_names = sorted(response)
                describe_resp = call_describe_parameters(
                    node=node, node_name=node_name, parameter_names=sorted_names
                )
                for descriptor in describe_resp.descriptors:
                    get_value_resp = call_get_parameters(
                        node=node,
                        node_name=node_name,
                        parameter_names=[descriptor.name],
                    )
                    parameters.append(
                        ParamInfo(
                            descriptor.name,
                            get_parameter_type_string(descriptor.type),
                            get_value(
                                parameter_value=get_value_resp.values[0]),
                        )
                    )

        env = Environment(
            loader=FileSystemLoader(
                get_package_share_directory("ros2model") + "/templates"
            ),
            autoescape=True,
        )
        template = env.get_template("node_model.jinja")
        contents = template.render(
            node_name=target_node_name,
            subscribers=subscribers,
            publishers=publishers,
            service_clients=service_clients,
            service_servers=service_servers,
            action_clients=action_clients,
            action_servers=action_servers,
            parameters=parameters,
            has_subscribers=len(subscribers) > 0,
            has_publishers=len(publishers) > 0,
            has_service_clients=len(service_clients) > 0,
            has_service_servers=len(service_servers) > 0,
            has_action_clients=len(action_clients) > 0,
            has_action_servers=len(action_servers) > 0,
            has_parameters=len(parameters) > 0,
            if_parameter_value=if_param_value,
        )
        print(contents)
        output_file = Path(output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        print("Writing model to {}".format(output_file.absolute()))
        output_file.touch()
        output_file.write_text(contents)

    def main(self, *, args):
        if not args.generate_all:
            if args.output != Path.cwd():
                self.create_a_node_model(
                    args.node_name, args.output, args.generate_value, args
                )
            else:
                self.create_a_node_model(
                    args.node_name, f"{args.node_name}.ros2", args.generate_value, args
                )
        else:
            with NodeStrategy(args) as node:
                for tmp_node in get_node_names(
                    node=node, include_hidden_nodes=args.include_hidden
                ):
                    if not re.search(r"transform_listener_impl", tmp_node.full_name):
                        self.create_a_node_model(
                            tmp_node.full_name,
                            f"{args.output_dir}/{tmp_node.name}.ros2",
                            args.generate_value,
                            args,
                        )
