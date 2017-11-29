class Chunk:


    def __init__(self, begin, end):
        self._begin = begin
        self._end = end


    def __lt__(self, other):
        return self._end < other._begin


    def __gt__ (self, other):
        return other < self


    def overlaps(self, other):
        return not (self < other or other < self)


    def intersect(self, other):
        assert(self.overlaps(other))
        begin = max(self._begin, other._begin)
        end = min(self._end, other._end)
        return Chunk(begin, end)


    def union(self, other):
        assert(self.overlaps(other))
        begin = min(self._begin, other._begin)
        end = max(self._end, other._end)
        return Chunk(begin, end)


    def __repr__(self):
        return "( {} to {} )".format(self._begin, self._end)




class Block:


    def __init__(self):
        self._chunks = [ ]


    def chunks(self):
        return self._chunks


    def serializable(self):
        result = []
        for chunk in self._chunks:
            result.append({"startTime": chunk._begin.format("MM/DD/YYYY HH:mm"), # Format to be human readable
                           "endTime": chunk._end.format("MM/DD/YYYY HH:mm")}) # Format to be human readable
        return result


    def append(self, chunk):
        self._chunks.append(chunk)


    def intersect(self, other):
        result = Block()
        for chunk in self._chunks:
            for o_chunk in other._chunks:
                if chunk.overlaps(o_chunk):
                    result.append(chunk.intersect(o_chunk))

        return result


    def merge(self):

        ordering = lambda c: c._begin
        self._chunks.sort(key=ordering)

        result = [ ]
        cur = self._chunks[0]

        for chunk in self._chunks[1:]:
            if chunk  > cur:
                result.append(cur)
                cur = chunk
            else:
                cur = cur.union(chunk)

        result.append(cur)
        self._chunks = result


    def merged(self):
        copy = Block()
        copy._chunks = self._chunks
        copy.merge()
        return copy


    def complement(self, free):
        copy = self.merged()
        comp = Block()
        cur = free._begin

        for chunk in copy._chunks:
            if chunk < free:
                continue
            if chunk > free:
                if cur < free._end:
                    comp.append(Chunk(cur, free._end))
                    cur = free._end
                break
            if cur < chunk._begin:
                comp.append(Chunk(cur, chunk._begin))
            cur = max(chunk._end, cur)
        if cur < free._end:
            comp.append(Chunk(cur, free._end))

        return comp


        def __iter__(self):
            return self._chunks.__iter__()
