#!/usr/bin/env python3
# Copyright 2013-present Barefoot Networks, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
############################################################################
# RDS-TUT jfpereira - Read all comments from this point on !!!!!!
############################################################################
# This code is given in 
# https://github.com/p4lang/behavioral-model/blob/main/mininet/1sw_demo.py
# with minor adjustments to satisfy the requirements of RDS-TP3. 
# This script works for a topology with one P4Switch connected to 253 P4Hosts. 
# In this TP3, we only need 1 P4Switch and 2 P4Hosts.
# The P4Hosts are regular mininet Hosts with IPv6 suppression.
# The P4Switch it's a very different piece of software from other switches 
# in mininet like OVSSwitch, OVSKernelSwitch, UserSwitch, etc.
# You can see the definition of P4Host and P4Switch in p4_mininet.py
###########################################################################
###########################################################################
#  Compile p4 
#  p4c-bm2-ss --p4v 16 p4/tut-simple-router.p4 -o json/tut-simple-router.json
#
#  Comando para correr:
#  sudo python mininet/topo_main.py --json json/tut-simple-router.json --topo-json json/topology.json 
#
#  Comando para limpar mininet:
#  sudo mn -c
###########################################################################


from mininet.net import Mininet
from mininet.topo import Topo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.node import OVSSwitch

from p4_mininet import P4Switch, P4Host

import argparse
from time import sleep
import json

# If you look at this parser, it can identify 4 arguments
# --behavioral-exe, with the default value 'simple_switch'
## this indicates that the arch of our software switch is the 'simple_switch'
## and any p4 program made for this arch needs to be compiled against de 'v1model.p4'
# --thrift-port, with the default value of 9090, which is the default server port of
## a thrift server - the P4Switch instantiates a Thrift server that allows us
## to communicate our P4Switch (software switch) at runtime
# --num-hosts, with default value 2 indicates the number of hosts...
# --json, is the path to JSON config file - the output of your p4 program compilation
## this is the only argument that you will need to pass in orther to run the script
parser = argparse.ArgumentParser(description='Mininet demo')
parser.add_argument('--behavioral-exe', help='Path to behavioral executable',
                    type=str, action="store", default='simple_switch')
parser.add_argument('--num-hosts', help='Number of hosts to connect to switch',
                    type=int, action="store", default=2)
parser.add_argument('--json', help='Path to JSON config file',
                    type=str, action="store", required=True)
parser.add_argument('--topo-json', help='Path to JSON topology file',
                    type=str, action="store", required=True)

args = parser.parse_args()

def parseTopology(file):
    with open(file) as f:
        parsed_data = json.load(f)
    return parsed_data


class Topology_generator(Topo):
    def __init__(self, sw_path, json_path, topology, **opts):
        # Initialize topology and default options
        Topo.__init__(self, **opts)
        topo_dict = {}
        r_ports = {}
        arr = []
        # Load topology
        for key in topology.keys():
            if key == "CONECTIONS":
                arr = topology[key]
            else:
                LAN = topology[key]
                if "Routers" in LAN:
                    for r in LAN["Routers"]:
                        router = self.addSwitch(r['NAME'],
                                            sw_path=sw_path,
                                            json_path=json_path,
                                            thrift_port=int(r['THRIFT_PORT']))
                        topo_dict[r['NAME']] = router
                        r_ports[r['NAME']] = r["PORTS"]
                        print("NEW ROUTER: " + r['NAME'])
                if "Switchs" in LAN:
                    for sw in LAN["Switchs"]:
                        switch = self.addSwitch(sw['NAME'], cls=OVSSwitch)
                        topo_dict[sw['NAME']] = switch
                        print("NEW SWITCH: " + sw['NAME'])
                if "Servers" in LAN:
                    for serv in LAN["Servers"]:
                        server = self.addHost(serv['NAME'],
                                            ip = serv['IP'],
                                            mac = serv['MAC'])
                        topo_dict[serv['NAME']] = server
                        print("NEW SERVER: " + serv['NAME'])
                if "Hosts" in LAN:
                    for h in LAN["Hosts"]:
                        host = self.addHost(h['NAME'],
                                            ip = h['IP'],
                                            mac = h['MAC'])
                        topo_dict[h['NAME']] = host
                        print("NEW HOST: " + h['NAME'])               
        for conn in arr:
            ep = conn.split(" <-> ")
            if "r" in ep[0] and "r" in ep[1]:
                r = ep[0].split(" ")
                aux = ep[1].split(" ")
                print(r[0], r_ports[r[0]][int(r[1])-1][1], aux[0], r_ports[aux[0]][int(aux[1])-1][1])
                self.addLink(topo_dict[r[0]], topo_dict[aux[0]], addr1=r_ports[r[0]][int(r[1])-1][1], addr2=r_ports[aux[0]][int(aux[1])-1][1])    
            elif "r" in ep[0]:
                r = ep[0].split(" ")
                print(r[0], r[1], r_ports[r[0]][int(r[1])-1][1])
                self.addLink(topo_dict[r[0]], topo_dict[ep[1]], addr1=r_ports[r[0]][int(r[1])-1][1])
            else:
                self.addLink(topo_dict[ep[0]], topo_dict[ep[1]])
            print("NEW CONN: "+ep[0]+" + "+ep[1])


def main():
    topology = parseTopology(args.topo_json)

    topo = Topology_generator(args.behavioral_exe,
                            args.json,
                            topology)

    # the host class is the P4Host
    # the switch class is the P4Switch
    net = Mininet(topo = topo,
                  host = P4Host,
                  switch = P4Switch,
                  controller = None)
    
    # Here, the mininet will use the constructor (__init__()) of the P4Switch class, 
    # with the arguments passed to the SingleSwitchTopo class in order to create 
    # our software switch.
    net.start()

    # h.setARP() populates the arp table of the host
    # h.setDefaultRoute() sets the defaultRoute for the host
    # populating the arp table of the host with the switch ip and switch mac
    # avoids the need for arp request from the host
    for lan in topology.keys():
        LAN = topology[lan]
        if "Hosts" in LAN:
            for h in LAN['Hosts']:
                h1 = net.get(h['NAME'])
                print("ARP- IP-"+h['DGW-IP']+" MAC-"+h['DGW-MAC'])
                #Set Arp
                h1.setARP(h['DGW-IP'], h['DGW-MAC'])
                #Set Default gateway
                h1.cmd("route add default gw {}".format(h['DGW-IP']))
                h1.describe()      
        if "Servers" in LAN:
            for srv in LAN["Servers"]:
                s = net.get(srv['NAME'])
                #Set Arp
                s.setARP(srv['DGW-IP'], srv['DGW-MAC'])
                #Set Default gateway
                s.cmd("route add default gw {}".format(srv['DGW-IP']))
                s.describe()
        if "Routers" in LAN:
            for r in LAN['Routers']:
                rt = net.get(r['NAME'])
                #Set commands
                comando = "simple_switch_CLI --thrift-port {} < {}".format(r['THRIFT_PORT'], r['COMMANDS'])
                rt.cmd(comando)
                print("Comando\n\t{}\nExecutado!".format(comando))
        if "Switchs" in LAN:
            for sw in LAN['Switchs']:
                sw1 = net.get(sw['NAME'])
                for rule in sw['RULES']:
                    comando = 'ovs-ofctl add-flow {} {}'.format(sw['NAME'],rule)
                    sw1.cmd(comando)
                    print("Comando:\n\t{}\nExecutado!".format(comando))
                

    sleep(1)  # time for the host and switch confs to take effect
    print("Ready !")
    CLI( net )
    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    main()