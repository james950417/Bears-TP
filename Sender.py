import sys
import getopt

import Checksum
import BasicSender

'''
This is a skeleton sender class. Create a fantastic transport protocol here.
'''
class Sender(BasicSender.BasicSender):
    def __init__(self, dest, port, filename, debug=False, sackMode=False):
        super(Sender, self).__init__(dest, port, filename, debug)
        self.sackMode = sackMode
        self.debug = debug

        self.window_size = 7
        self.data_chunk_size = 1400
        self.timeout = 0.5  # 500 ms

        self.current_msg = self.infile.read(self.data_chunk_size)
        self.next_msg = self.infile.read(self.data_chunk_size)
        self.window = dict()
        self.sent = dict()
        self.sack_received = dict()

        self.next_seq_no = 1
        self.same_ack_times = 0
        self.fin_seqno = 0

        self.finished_chunking = False
        self.all_acked = False

    # Main sending loop.
    def start(self):
        self.start_with_syn()
        while (self.all_acked == False):
            self.construct_window()
            self.send_window()
            response = self.receive(self.timeout)
            self.handle_response(response)
        if (self.all_acked == True):
            return 

    # Helper function: first send the syn packet to the receiver and make sure it is acknowledged
    def start_with_syn(self):
        syn_packet = self.make_packet('syn', 0, "")
        self.send(syn_packet)
        response = self.receive(self.timeout)
        if self.sackMode == False:
            if ((response == None) or (Checksum.validate_checksum(response) == False) or (self.split_packet(response)[1] != '1')):
                self.start_with_syn()
            self.sent[self.next_seq_no] = True
        elif self.sackMode == True:
            if ((response == None) or (Checksum.validate_checksum(response) == False) or ((self.split_packet(response)[1]).split(";")[0] != '1')):
                self.start_with_syn()
            self.sent[self.next_seq_no] = True


    def construct_window(self):
        if len(self.window) == self.window_size:
            return
        while len(self.window) < self.window_size and self.finished_chunking == False:
            if self.next_msg != "":
                packet_type = 'dat'
            else:
                packet_type = 'fin'
                self.finished_chunking = True
                self.fin_seqno = self.next_seq_no
            new_packet = self.make_packet(packet_type, self.next_seq_no, self.current_msg)
            self.window[self.next_seq_no] = new_packet
            self.sent[self.next_seq_no] = False
            self.next_seq_no += 1
            self.current_msg = self.next_msg
            self.next_msg = self.infile.read(self.data_chunk_size)


    def send_window(self):
        for seq_no, packet in self.window.items():
            if self.sent[seq_no] == False:
                self.send(packet)
                self.sent[seq_no] = True
                if self.sackMode == True:
                    self.sack_received[seq_no] = False


    def handle_response(self, response_packet):
        if self.sackMode == False:
            if (response_packet == None):
                self.handle_timeout_ack()
            if (Checksum.validate_checksum(response_packet) == False):
                return
            msg_type, seqno, data, checksum = self.split_packet(response_packet)
            seqno = int(seqno)
            if seqno == min(self.window.keys()):
                self.handle_duplicated_seqno(seqno)
            else:
                self.handle_new_seqno(seqno)

        elif self.sackMode == True:
            if (response_packet == None):
                self.handle_timeout_sack()
            else:
                msg_type, sack, data, checksum = self.split_packet(response_packet)
                self.handle_sack(sack)
            return


    def handle_duplicated_seqno(self, seqno):
        if self.same_ack_times >= 3:
            self.sent[seqno] = False
        else:
            self.same_ack_times += 1


    def handle_new_seqno(self, seqno):
        for seq_no in self.window.keys():
            if seqno > seq_no:
                del self.window[seq_no]
                del self.sent[seq_no]
                self.same_ack_times = 0
            if self.finished_chunking == True and seqno == (self.fin_seqno + 1):
                self.all_acked = True


    def handle_sack(self, sack):
        seqno = int(sack.split(";")[0])
        if sack.split(";")[1]:
            received_string = (sack.split(";")[1]).split(",")
            temp_list = []
            for a in received_string:
                temp_list.append(int(a))
        if seqno == min(self.window.keys()):
            if sack.split(";")[1]:
                for b in temp_list:
                    self.sack_received[b] = True

        else:
            for seq_no in self.window.keys():
                if seqno > seq_no:
                    self.sack_received[seq_no] = True
                    del self.window[seq_no]
                    del self.sent[seq_no]
                if sack.split(";")[1]:
                    for b in temp_list:
                        self.sack_received[b] = True
                if self.finished_chunking == True and seqno == (self.fin_seqno + 1):
                    self.all_acked = True


    def handle_timeout_sack(self):
        for seqnos in self.window.keys():
            if self.sack_received[seqnos] == False:
                self.sent[seqnos] = False


    def handle_timeout_ack(self):
        for seq_no in self.window.keys():
            self.sent[seq_no] = False  
      
        
'''
This will be run if you run this script from the command line. You should not
change any of this; the grader may rely on the behavior here to test your
submission.
'''
if __name__ == "__main__":
    def usage():
        print "BEARS-TP Sender"
        print "-f FILE | --file=FILE The file to transfer; if empty reads from STDIN"
        print "-p PORT | --port=PORT The destination port, defaults to 33122"
        print "-a ADDRESS | --address=ADDRESS The receiver address or hostname, defaults to localhost"
        print "-d | --debug Print debug messages"
        print "-h | --help Print this usage message"
        print "-k | --sack Enable selective acknowledgement mode"

    try:
        opts, args = getopt.getopt(sys.argv[1:],
                               "f:p:a:dk", ["file=", "port=", "address=", "debug=", "sack="])
    except:
        usage()
        exit()

    port = 33122
    dest = "localhost"
    filename = None
    debug = False
    sackMode = False

    for o,a in opts:
        if o in ("-f", "--file="):
            filename = a
        elif o in ("-p", "--port="):
            port = int(a)
        elif o in ("-a", "--address="):
            dest = a
        elif o in ("-d", "--debug="):
            debug = True
        elif o in ("-k", "--sack="):
            sackMode = True

    s = Sender(dest,port,filename,debug, sackMode)
    try:
        s.start()
    except (KeyboardInterrupt, SystemExit):
        exit()
