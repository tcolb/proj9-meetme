import nose, arrow
from times import Chunk, Block


#
#  GLOBAL VARS
#


chunk_1 = Chunk(arrow.get("2017-11-16T09:00:00-08:00"),
                arrow.get("2017-11-16T17:00:00-08:00"))
chunk_2 = Chunk(arrow.get("2017-11-16T12:00:00-08:00"),
                arrow.get("2017-11-16T20:00:00-08:00"))
chunk_3 = Chunk(arrow.get("2017-11-16T02:00:00-08:00"),
                arrow.get("2017-11-16T20:00:00-08:00"))


#
#  CHUNK TESTING
#


def test_chunk_initialization():

    time_1 = arrow.get("2017-11-16T09:00:00-08:00")
    time_2 = arrow.get("2017-11-16T17:00:00-08:00")
    chunk = Chunk(time_1, time_2)

    # Testing start and end times
    assert chunk._begin == time_1
    assert chunk._end == time_2

    print("Chunk initialization working!")


#
#  BLOCK TESTING
#


def test_block_initialization():

    cks = [ chunk_4 = Chunk(arrow.get("2017-11-16T02:00:00-08:00"),
                            arrow.get("2017-11-16T06:00:00-08:00"))
                      Chunk(arrow.get("2017-11-16T04:00:00-08:00"),
                            arrow.get("2017-11-16T08:00:00-08:00"))
                      Chunk(arrow.get("2017-11-16T10:00:00-08:00"),
                            arrow.get("2017-11-16T18:00:00-08:00"))
                      Chunk(arrow.get("2017-11-16T12:00:00-08:00"),
                            arrow.get("2017-11-16T20:00:00-08:00")) ]


    # Test to see if blocks combine chunks at init
    block = Block()
    [ block.append(chunk) for chunk in cks ]
    assert block.chunks() == [ Chunk(arrow.get("2017-11-16T02:00:00-08:00"),
                                     arrow.get("2017-11-16T20:00:00-08:00")) ]

    print("Block initialiation working!")
