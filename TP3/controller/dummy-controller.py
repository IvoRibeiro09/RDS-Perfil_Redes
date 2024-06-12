#!/usr/bin/env python3
import argparse
import json
import os
import sys
from time import sleep

import grpc

# Import P4Runtime lib from utils dir
# Probably there's a better way of doing this.
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),'../utils/'))

import p4runtime_lib.bmv2
import p4runtime_lib.helper
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections


def printGrpcError(e):
    print("gRPC Error:", e.details(), end=' ')
    status_code = e.code()
    print("(%s)" % status_code.name, end=' ')
    traceback = sys.exc_info()[2]
    print("[%s:%d]" % (traceback.tb_frame.f_code.co_filename, traceback.tb_lineno))

def readTableRules(p4info_helper, sw):
    """
    Reads the table entries from all tables on the switch.

    :param p4info_helper: the P4Info helper
    :param sw: the switch connection
    """
    print('\n----- Reading tables rules for %s -----' % sw.name)
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            # you can use the p4info_helper to translate
            # the IDs in the entry to names
            table_name = p4info_helper.get_tables_name(entry.table_id)
            print('%s: ' % table_name, end=' ')
            for m in entry.match:
                print(p4info_helper.get_match_field_name(table_name, m.field_id), end=' ')
                print('%r' % (p4info_helper.get_match_field_value(m),), end=' ')
            action = entry.action.action
            action_name = p4info_helper.get_actions_name(action.action_id)
            print('->', action_name, end=' ')
            for p in action.params:
                print(p4info_helper.get_action_param_name(action_name, p.param_id), end=' ')
                print('%r' % p.value, end=' ')
            print()

def writeSrcMac(p4info_helper, sw, port_mac_mapping):
    for port, mac in port_mac_mapping.items():
        table_entry = p4info_helper.buildTableEntry(
            table_name="MyIngress.src_mac",
            match_fields={
                "standard_metadata.egress_spec": port
            },
            action_name="MyIngress.rewrite_src_mac",
            action_params={
                "src_mac": mac
            })
        sw.WriteTableEntry(table_entry)
    print("Installed MAC SRC rules on %s" % sw.name)


def writeFwdRules(p4info_helper, sw, dstAddr, mask, nextHop, port, dstMac):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": (dstAddr, mask)
        },
        action_name="MyIngress.ipv4_fwd",
        action_params={
            "nxt_hop": nextHop,
            "port": port
        })
    sw.WriteTableEntry(table_entry)

    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.dst_mac",
        match_fields={
            "meta.next_hop_ipv4": nextHop
        },
        action_name="MyIngress.rewrite_dst_mac",
        action_params={
            "dst_mac": dstMac
        })
    sw.WriteTableEntry(table_entry)
    print("Installed FWD rule on %s" % sw.name)

def writeTcpFlow(p4info_helper, sw, src_Addr, dst_Addr, src_Range, dst_Range):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.tcp_flow",
        match_fields={
            "hdr.ipv4.srcAddr": src_Addr,
            "hdr.ipv4.dstAddr": dst_Addr,
            "hdr.tcp.srcPort": src_Range,
            "hdr.tcp.dstPort": dst_Range,
        },
        action_name="NoAction",
        action_params={
            "id": 1
        })
    print("Ola")
    sw.WriteTableEntry(table_entry)
    print("Installed TCP FLOW rules on %s" % sw.name)

def writeIcmpFlow(p4info_helper, sw, dst_Addr, mask, nextHop, dstMac):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.icmp_flow",
        match_fields={
            "hdr.ipv4.dstAddr": (dst_Addr, mask),
        },
        action_name="MyIngress.reply",
        action_params={
            "nxt_hop": nextHop,
            "nt_mac": dstMac     
        })
    sw.WriteTableEntry(table_entry)
    print("Installed ICMP FLOW rules on %s" % sw.name)

def printCounter(p4info_helper, sw, counter_name, index):
    for response in sw.ReadCounters(p4info_helper.get_counters_id(counter_name), index):
        for entity in response.entities:
            counter = entity.counter_entry
            print("%s %s %d: %d packets (%d bytes)" % (
                sw.name, counter_name, index,
                counter.data.packet_count, counter.data.byte_count
            ))


def main(p4info_file_path, bmv2_file_path, json_file, rules):
    # Instantiate a P4Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)
    routers = []

    try:
        # this is backed by a P4Runtime gRPC connection.
        # Also, dump all P4Runtime messages sent to switch to given txt files.
        for router in json_file:
            print(router)
            r = p4runtime_lib.bmv2.Bmv2SwitchConnection(
                name= router["Name"],
                address= router["Address"],
                device_id= int(router["ID"]),
                proto_dump_file= router["proto_dump_file"])
            routers.append(r)
        print("connection successful")

        # Send master arbitration update message to establish this controller as
        # master (required by P4Runtime before performing any other write operation)
        for r in routers: r.MasterArbitrationUpdate()

        # Install the P4 program on the switches
        for r in routers:
            r.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
            print("Installed P4 Program using SetForwardingPipelineConfig on ", r.name)
        
        # Set mac addresses of router 
        for r in routers:
            j = 1
            dic = {}
            for i in rules[r.name]["writeSrcMac"]:
                dic[j] = i
                j+=1
            print(dic)
            writeSrcMac(p4info_helper, r, dic)

        # IPV4 foward rules
        # writeFwdRules(p4info_helper, sw, dstAddr, mask, nextHop, port, dstMac)
        for r in routers:
            for fwd_rule in rules[r.name]["writeFwdRules"]:
                print(fwd_rule)
                writeFwdRules(p4info_helper, r, fwd_rule[0], fwd_rule[1], fwd_rule[2], fwd_rule[3], fwd_rule[4])
        
        # TCP FLOW rules
        # writeTcpFlow(p4info_helper, sw, src_Addr, dst_Addr, src_Port, dst_Port)
        for r in routers:
            for rule in rules[r.name]["writeTcpFlow"]:
                print(rule)
                #writeTcpFlow(p4info_helper, r, rule[0], rule[1], (rule[2], rule[3]), (rule[4], rule[5]))
        
        # ICMP FLOW rules
        # writeTcpFlow(p4info_helper, sw, src_Addr, dst_Addr, src_Port, dst_Port)
        for r in routers:
            for rule in rules[r.name]["writeIcmpFlow"]:
                print(rule)
                writeIcmpFlow(p4info_helper, r, rule[0], rule[1], rule[2], rule[3])


        # Read tables 
        for r in routers: 
            readTableRules(p4info_helper, r)

        # Show run time
        while True:
            sleep(10)
            print('\n----- Reading counters -----')
            for r in routers:
                printCounter(p4info_helper, r, "MyIngress.c", 1)
            #printCounter(p4info_helper, r2, "MyIngress.c", 1)

    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)

def parseTopology(file):
    with open(file) as f:
        parsed_data = json.load(f)
    return parsed_data

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='build/s-router.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='build/s-router.json')
    parser.add_argument('--json', help='Path to JSON topology file',
                        type=str, action="store", required=False,
                        default="json/controller.json")
    parser.add_argument('--rules', help='Path to JSON rules file',
                        type=str, action="store", required= False, 
                        default="json/rules.json")
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found:")
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found:")
        parser.exit(1)

    main(args.p4info, args.bmv2_json, parseTopology(args.json), parseTopology(args.rules))