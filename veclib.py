from difflib import get_close_matches
import pandas as pd
import numpy as np
import os.path
import string
import difflib
import unicodedata
import numexpr as ne
import time
from sets import Set 
from utils import *

""" A library to lookup word vectors, reduce the vector list to a subset and
calculate the nearest word given a vector"""

trained = "/u/cmoody3/data2/ids/trained"
fnw = '%s/vectors.bin.008.words' % trained
fnv = '%s/vectors.bin.008.num' % trained
fnc = 'data/movies_canonical'
def distance(v1, v2, axis=None):
    if type(v1) is str:
        v1 = lookup_vector(v1)
    if type(v2) is str:
        v2 = lookup_vector(v2)
    if len(v1.shape[0]) > 1:
        axis = 1
    i = (v1.astype(np.float64) - v2.astype(np.float64))**2.0
    d = np.sqrt(np.sum(i, axis=axis, dtype=np.float128))
    return d

def reshape(v1):
    if len(v1.shape) == 1:
        shape = [1, v1.shape[0]]
        v1 = np.reshape(v1, shape)
    return v1

def mag(x):
    return np.sqrt(np.sum(x**2.0, axis=1))

mag2 = lambda x: np.sqrt(np.sum(x**2.0, axis=1))
mag1 = lambda x: np.sqrt(np.sum(x**2.0, axis=0))
def similarity(svec, total):
    smv = np.reshape(total, (1, total.shape[0]))
    top = svec * smv
    denom = mag2(svec) * mag1(total)
    denom = np.reshape(denom, (denom.shape[0], 1))
    sim = np.sum(top / denom, axis=1)
    return sim

@timer
def normalize(avl):
    vnorm = ne.evaluate('sum(avl**2.0, axis=1)')
    vnorm.shape = [vnorm.shape[0], 1]
    avl = ne.evaluate('avl / sqrt(vnorm)')
    return avl

def chunks(l, n):
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

def in_between(vectora, vectorb, vector_lib, index2word, n=10):
    #Measure rough dispersion in each dimension
    dispersion = np.abs(vectorb - vectora)
    vectora = np.reshape(vectora, (1, vectora.shape[0]))
    vectorb = np.reshape(vectorb, (1, vectorb.shape[0]))
    dist = np.minimum(np.abs(vector_lib - vectora),
                      np.abs(vector_lib - vectorb))
    idx = np.argsort(dist)
    words = [index2word[idx[i]] for i in range(n)]
    return dist / dispersion

def nearest_word(vector, vector_lib, index2word, n=5, skip=0, 
                 chunk_size=100000, use_ne=True):
    words = []
    if use_ne:
        d = ne.evaluate('sum(vector_lib * vector, axis=1)')
        idx = np.argsort(d)[::-1]
        words = [index2word[i] for i in idx[:n]]
    else:
        sims = []
        offset = 0
        for vl in chunks(vector_lib, chunk_size):
            d = similarity(vl, vector)
            da = np.argsort(d)[::-1]
            for idx in da[:n]:
                words.append(index2word[idx + offset])
                sims.append(d[idx])
            offset += chunk_size
        idx = np.argsort(sims)[::-1]
        words = [words[i] for i in idx[:n]]
    return words

@timer
def subsample(avl, w2i, i2w, whitelist, n):
    subw2i = {}
    subi2w = {}
    count = 0
    for i in range(len(avl)):
        word = i2w[i]
        if count < n or '_' in word or word in whitelist:
            subi2w[i] = word
            subw2i[word] = count
            count +=1
    indices = subi2w.keys()
    subavl = avl[indices]
    return subavl, subw2i, subi2w

@timer
def lookup_vector(word, vector_lib, w2i, fuzzy=True):
    keys = w2i.keys()
    if word not in keys:
        key, = get_close_matches(word, keys, 1)
    else:
        key = word
    print 'Lookup: %s -> %s' % (word, key)
    return vector_lib[w2i[key]]

@timer
def get_canon_rep(fn):
    c2f, f2c = {}, {}
    with open(fn) as fh:
        for line in fh.readlines():
            line = line.strip()
            line = line.replace('  ', ' ')
            f, c = line.rsplit(',', 1)
            f, c = f.strip(), c.strip()
            c2f[c] = f
            f2c[f] = c
    return c2f, f2c

def canonize(phrase, c2f, match=True, subset=False):
    phrase = phrase.replace('\n','').replace('\t','').replace('\r','')
    for i in range(5):
        phrase = phrase.replace('  ', ' ')
    phrase = phrase.strip()
    phrase = phrase.replace(' ', '_')
    phrase = phrase.strip().lower()
    keys = Set(c2f.keys())
    if phrase in keys: return phrase
    phrase = phrase.replace('-', '_')
    for p in string.punctuation:
        phrase = phrase.replace(p, '')
    if phrase in keys: return phrase
    phrase = phrase.replace(' ', '_')
    if phrase in keys: return phrase
    if not match:
        return phrase
    first = phrase.split(' ')[0]
    if subset:
        sub = Set((first in k for k in keys))
    else:
        sub = keys
    phrase, = difflib.get_close_matches(phrase, sub, 1)
    phrase = unicodedata.normalize('NFKD', unicode(phrase)).encode('ascii','ignore')
    return phrase

@timer
def reduce_vectorlib(vector_lib, word2index, canon):
    indices = []
    w2i, i2w = {}, {}
    outindex = 0
    words = Set(word2index.keys())
    common = Set(canon).intersection(words)
    for name in common:
        index = word2index[name]
        indices.append(index)
        w2i[name] = outindex
        i2w[outindex] = name
        outindex += 1
    indices = np.array(indices)
    rvl = vector_lib[indices]
    return rvl, w2i, i2w

@timer
def get_names(fn=fnc):
    names = [x.replace('\n', '').strip() for x in fh.readlines()]
    text = ''.join(names)
    text = text.replace('\n', '')
    return text

@timer
def get_words(fn=fnw, subsample=None):
    words = open(fn).readlines()
    word2index = {}
    index2word = {}
    for v, k in enumerate(words):
        k = k.strip().replace('\n', '')
        if subsample:
            if v > subsample - 1:
                break
        index2word[v] = k
        word2index[k] = v
        k = canonize(k, {}, match=False)
        word2index[k] = v
    return word2index, index2word

@timer
def get_english(fn):
    words = []
    with open(fn) as fh:
        for line in fh.readlines():
            words.append(line.strip())
    return words

@timer
def get_vector_lib(fn=fnv):
    fnvn = fn.replace('.npy', '')
    if not os.path.exists(fn) and os.path.exists(fnvn):
        data = pd.read_csv(fn, sep=' ',
                           dtype='f4', na_filter=False)
        data = np.array(data, dtype=np.float32)
        np.save(fn, data)
        return data
    else:
        vectors = np.load(fn)
        return vectors