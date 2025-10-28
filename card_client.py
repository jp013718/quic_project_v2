import argparse
import asyncio
import ssl

import aioquic.asyncio
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

from PIL import Image

class CardClient(aioquic.asyncio.QuicConnectionProtocol):
  # Initialize stream buffers
  stream_buffers = {}
  
  def quic_event_received(self, quic_event):
    if isinstance(quic_event, StreamDataReceived):
      # Add stream data to the respective stream's buffer
      data = quic_event.data
      self.stream_buffers[quic_event.stream_id] += data

      if quic_event.end_stream:
        # If the stream is complete, process the image
        self.process_images(quic_event.stream_id)
        # If that was the last stream, end the connection
        if not self.stream_buffers:
          self.time.set_result(self._loop.time() - self.start_time)

  def transfer(self, data):
    # Get the next available stream id and use it to send a request
    stream_id = self._quic.get_next_available_stream_id()
    self._quic.send_stream_data(
      stream_id=stream_id,
      data=bytes(data, encoding='utf-8'),
      end_stream=True,
    )
    # Initialize the buffer for the new stream id
    self.stream_buffers[stream_id] = b''
    self.transmit()

  def process_images(self, stream_id):
    # Grab the image bytes from the stream buffer
    img_bytes = self.stream_buffers[stream_id]
    # Check if the received image is a single-faced card
    if len(img_bytes) == 1886976:
      image = Image.frombytes("RGB", (672, 936), img_bytes)
      image.show()
    # Check if the received image is a double-faced card
    elif len(img_bytes) == 3773952:
      img_front_bytes = img_bytes[:1886976]
      img_back_bytes = img_bytes[1886976:]
      image_front = Image.frombytes("RGB", (672, 936), img_front_bytes)
      image_back = Image.frombytes("RGB", (672, 936), img_back_bytes)
      image_front.show()
      image_back.show()
    # Otherwise, the received data must be a "Card not found" error
    else:
      error = img_bytes.decode('utf-8')
      print(error)

    # Delete the stream buffer once the image (or error) has been processed
    del self.stream_buffers[stream_id]

  def process_arguments(self, data):
    # Handle the arguments; send each card request in its own stream
    for card_name in data[0]:
      self.transfer(card_name)
    for _ in range(data[1]):
      self.transfer('-r')

    self.start_time = self._loop.time()
    self.time = self._loop.create_future()
    return self.time
    

async def main(data, host='127.0.0.1', port=9999):
  async with aioquic.asyncio.connect(
    host,
    port,
    configuration=QuicConfiguration(verify_mode=ssl.CERT_NONE),
    create_protocol=CardClient,
  ) as client:
    await client.process_arguments(data)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-H', '--host', type=str, default='127.0.0.1')
  parser.add_argument('-p', '--port', type=int, default=9999)
  parser.add_argument('-n', '--name', nargs='+', action='extend', type=str, default=[])
  parser.add_argument('-r', '--random', type=int, default=0)
  args = parser.parse_args()

  host = args.host
  port = args.port
  card_names = args.name
  n_random_cards = args.random

  data = (card_names, n_random_cards)

  asyncio.run(
    main(
      data,
      host,
      port,
    )
  )