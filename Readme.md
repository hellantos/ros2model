# ROS Model integration into ROS2 Command

### Create ".ros" file for the interface package.
#### Create a ".ros" model for an interface package.
```
ros2 model interface_package [-o Outputfile] <package-name>
```
#### Create ".ros" models for all interface package in the workspace.

```
ros2 model interface_package -a -o <folder-name>
```

```
ros2 model running_node [-o Outputfile] <node-name>
```
Creates a partial .ros2 file for the running node, only the node specific part. The node must be running.

