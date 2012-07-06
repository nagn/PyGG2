from __future__ import division, print_function

# add our main folder as include dir
import sys
sys.path.append("../")

import socket
import constants
import networking.packet
import networking.event_serialize
import event_handler

class Networker(object):
    def __init__(self, server_address, client):
        self.server_address = server_address

        self.events = []
        self.sendbuffer = []
        self.sequence = 1
        self.server_acksequence = 0
        self.client_acksequence = 0

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("", 0))
        self.socket.setblocking(False)

        self.has_connected = False
        self.connection_timeout_timer = constants.CLIENT_TIMEOUT

        # Connect to the server, or at least send the hello
        packet = networking.packet.Packet("client")
        packet.sequence = self.sequence
        packet.acksequence = self.client_acksequence

        event = networking.event_serialize.ClientEventHello(client.player_name, client.server_password)
        packet.events.append((self.sequence, event))
        data = packet.pack()

        numbytes = self.socket.sendto(data, self.server_address)
        if len(data) != numbytes:
            # TODO sane error handling
            print("SERIOUS ERROR, NUMBER OF BYTES SENT != PACKET SIZE AT HELLO")
            
        self.current_pint = 0.0

    def recieve(self, game, client):
        # If we haven't received confirmation that we're connected yet, see if we should try again:
        if not self.has_connected:
            self.connection_timeout_timer -= 1

            if self.connection_timeout_timer <= 0:
                self.connection_timeout_timer = constants.CLIENT_TIMEOUT
                # Send a reminder, in case the first packet was lost
                packet = networking.packet.Packet("client")
                packet.sequence = self.sequence
                packet.acksequence = self.client_acksequence

                event = networking.event_serialize.ClientEventHello(client.player_name, client.server_password)
                packet.events.append((self.sequence, event))
                data = packet.pack()

                numbytes = self.socket.sendto(data, self.server_address)
                if len(data) != numbytes:
                    # TODO sane error handling
                    print("SERIOUS ERROR, NUMBER OF BYTES SENT != PACKET SIZE AT HELLO")


        while True:
            packet = networking.packet.Packet("server")

            try:
                data, sender = self.socket.recvfrom(constants.MAX_PACKET_SIZE)
            except socket.error:
                # recvfrom throws socket.error if there was no packet to read
                break

            # FIXME: Uncomment these as soon as networking debugging is done. I commented this out because it messed with Traceback.
            #try:
            packet.unpack(data)
            #except:
            #    # parse error, don't throw exception but print it
            #    print("Parse error: %s" % sys.exc_info()[1])
            #    continue # drop packet

            # only accept the packet if the sender is the server
            if sender == self.server_address:
                for seq, event in packet.events:
                    if seq <= self.client_acksequence:
                        # Event has already been processed before, discard
                        continue
                    # process the event
                    event_handler.eventhandlers[event.eventid](client, self, game, event)
            # otherwise drop the packet
            else:
                print("RECEIVED PACKET NOT FROM ACTUAL SERVER ADDRESS:\nActual Server Address:"+str(self.server_address)+"\nPacket Address:"+str(sender))
                continue

            # ack the packet
            self.client_acksequence = packet.sequence
            self.server_acksequence = packet.acksequence

            # Clear the acked stuff from the history
            index = 0
            while index < len(self.events):
                seq, event = self.events[index]
                if seq > self.server_acksequence:
                    # This (and all the following events) weren't acked yet. We're done.
                    break
                else:
                    del self.events[index]
                    index -= 1
                index += 1


    def generate_inputdata(self, client):
        our_player = client.game.current_state.players[client.our_player_id]
        packetstr = our_player.serialize_input()
        event = networking.event_serialize.ClientEventInputstate(packetstr)
        return event


    def update(self, client):
        # Unload the whole sendbuffer here, and add the sequence
        for event in self.sendbuffer:
            self.events.append((self.sequence, event))
        self.sendbuffer = []

        packet = networking.packet.Packet("client")
        packet.sequence = self.sequence
        packet.acksequence = self.client_acksequence

        for seq, event in self.events:
            packet.events.append((seq, event))

        if not client.destroy:
            # Prepend the input data if we're not disconnecting
            packet.events.insert(0, (self.sequence, self.generate_inputdata(client)))

        packetstr = ""
        packetstr += packet.pack()

        numbytes = self.socket.sendto(packetstr, self.server_address)
        if len(packetstr) != numbytes:
            # TODO sane error handling
            print("SERIOUS ERROR, NUMBER OF BYTES SENT != PACKET SIZE")
        
        self.current_ping = ((self.sequence - self.server_acksequence) * constants.INPUT_SEND_FPS)
        print(self.current_ping * 1000)
        self.sequence = (self.sequence + 1) % 65535
        
