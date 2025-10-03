import socket
import sys
import time
import random

def main():
    if len(sys.argv) != 3:
        print(f"Usage: python3 {sys.argv[0]} <host> <port>")
        sys.exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(0.6) 

    seq_start = random.randint(40000, 50000)
    num_pings = 15

    rtts = []
    timeouts = 0
    prev_rtt = None
    jitters = []

    start_time = time.time()
    for i in range(num_pings):
        seq = seq_start + i
        timestamp = time.time()
        message = f"PING {seq} {timestamp}"
        client_socket.sendto(message.encode(), (host, port))
        send_time = time.time()

        try:
            data, _ = client_socket.recvfrom(1024)
            recv_time = time.time()
            rtt = (recv_time - send_time) * 1000
            rtts.append(rtt)

            if prev_rtt is not None:
                jitters.append(abs(rtt - prev_rtt))
            prev_rtt = rtt

            print(f"PING to {host}, seq={seq}, rtt={int(rtt)} ms, timestamp={int(recv_time * 1000)} ms")
        except socket.timeout:
            timeouts += 1
            print(f"PING to {host}, seq={seq}, rtt=timeout, timestamp={int(time.time() * 1000)} ms")

    end_time = time.time()
    client_socket.close()

    received = len(rtts)
    lost = timeouts
    loss_percent = lost / num_pings * 100

    if received > 0:
        min_rtt = min(rtts)
        max_rtt = max(rtts)
        avg_rtt = sum(rtts) / received
    else:
        min_rtt = max_rtt = avg_rtt = 0

    total_time = (end_time - start_time) * 1000
    jitter = sum(jitters) / len(jitters) if jitters else 0

    print()
    print(f"Packet loss: {loss_percent:.2f}%")
    print(f"Minimum RTT: {int(min_rtt)} ms, Maximum RTT: {int(max_rtt)} ms, Average RTT: {int(avg_rtt)} ms")
    print(f"Total transmission time: {int(total_time)} ms")
    print(f"Jitter: {int(jitter)} ms")

if __name__ == "__main__":
    main()
