import numpy as np
import tensorflow as tf
import time
import pickle

FLAGS = tf.app.flags.FLAGS
NUM_CLOZES = 1

# Model Parameters
tf.app.flags.DEFINE_integer(
    'num_steps', 1, 'Number of unrolled steps before backprop.')
tf.app.flags.DEFINE_integer('embedding_size', 50, 'Size of the Embeddings.')
tf.app.flags.DEFINE_integer('hidden_size', 256, 'Size of the LSTM Layer.')

# Training Parameters
tf.app.flags.DEFINE_integer('num_epochs', 1, 'Number of Training Epochs.')
tf.app.flags.DEFINE_integer(
    'batch_size', 20, 'Size of a batch (for training).')
tf.app.flags.DEFINE_float('learning_rate', 1e-4,
                          'Learning rate for Adam Optimizer.')
tf.app.flags.DEFINE_float(
    'dropout_prob', 0.5, 'Keep probability, for dropout.')
tf.app.flags.DEFINE_integer(
    'eval_every', 10000, 'Print statistics every eval_every words.')


class RNNLangmod():
    def __init__(self, vocab_size, embedding_size, num_steps, hidden_size,
                 batch_size, learning_rate):
        """
        Instantiate an RNNLangmod Model, with the necessary hyperparameters.

        :param vocab_size: Size of the vocabulary.
        :param num_steps: Number of words to feed into LSTM before performing
        a gradient update.
        :param hidden_size: Size of the LSTM Layer.
        :param num_layers: Number of stacked LSTM Layers in the model.
        :param batch_size: Batch size (for training).
        :param learning_rate: Learning rate for Adam Optimizer
        """
        self.vocab_size, self.embedding_size = vocab_size, embedding_size
        self.hidden, self.num_steps = hidden_size, num_steps
        self.bsz, self.learning_rate = batch_size, learning_rate

        # Setup Placeholders
        self.X = tf.placeholder(tf.int32, shape=[None, self.num_steps])
        self.Y = tf.placeholder(tf.int32, shape=[None, self.num_steps])
        self.keep_prob = tf.placeholder(tf.float32)

        # Instantiate Network Weights
        self.instantiate_weights()

        # Build the Inference Graph
        self.logits, self.final_state = self.inference()

        # Build the Loss Computation
        self.loss_val = self.loss()

        # Build the Training Operation
        self.train_op = self.train()

    def instantiate_weights(self):
        # Embedding Matrix
        self.E = self.weight_variable(
            [self.vocab_size, self.embedding_size], 'Embedding')

        # Basic LSTM Cell
        self.cell = tf.nn.rnn_cell.BasicLSTMCell(self.hidden)
        self.initial_state = self.cell.zero_state(self.bsz, tf.float32)

        # Softmax Output
        self.softmax_w = self.weight_variable(
            [self.hidden, self.vocab_size], 'Softmax_Weight')
        self.softmax_b = self.weight_variable(
            [self.vocab_size], 'Softmax_Bias')

    def inference(self):
        """
        Build the inference computation graph for the model, going
        from the input to the output logits (before final softmax
        activation).

        :return Tuple of 2D Logits Tensor [bsz * steps, vocab],
        and Final State [num_layers]
        """
        # Feed input through the Embedding Layer, Dropout.
        # Shape [bsz, steps, hidden]
        emb = tf.nn.embedding_lookup(self.E, self.X)
        drop_emb = tf.nn.dropout(emb, self.keep_prob)

        # Feed input through dynamic_rnn
        # Shape [bsz, steps, hidden]
        out, f_state = tf.nn.dynamic_rnn(self.cell, drop_emb,
                                         initial_state=self.initial_state)

        # Reshape the outputs into a single 2D Tensor
        # Shape [bsz * steps, hidden]
        outputs = tf.reshape(out, [-1, self.hidden])

        # Feed through final layer, compute logits
        logits = tf.matmul(outputs, self.softmax_w) + \
            self.softmax_b   # Shape [bsz * steps, vocab]
        return logits, f_state

    def loss(self):
        seq_loss = tf.nn.seq2seq.sequence_loss_by_example(
            [self.logits],
            [tf.reshape(self.Y, [-1])],
            [tf.ones([self.bsz * self.num_steps])])
        loss = tf.reduce_sum(seq_loss) / self.bsz
        return loss

    def train(self):
        optimizer = tf.train.AdamOptimizer(self.learning_rate)
        return optimizer.minimize(self.loss_val)

    @staticmethod
    def weight_variable(shape, name):
        initial = tf.truncated_normal(shape, stddev=0.1)
        return tf.Variable(initial, name=name)

    @staticmethod
    def bias_variable(shape, name):
        initial = tf.constant(0.1, shape=shape)
        return tf.Variable(initial, name=name)


def read_cloze(i):
    x = np.array(clozes_data[i]['text_v'][:-1], dtype=int)
    y = np.array(clozes_data[i]['text_v'][1:], dtype=int)
    choices = clozes_data[i]['choices_v']
    keys = clozes_data[i]['keys_v']
    return x, y, choices, keys


def read_training():
    with open('books_training', 'rb') as f:
        books_training = pickle.load(f)
    x = np.array(books_training[:-1])
    y = np.array(books_training[1:])
    return x, y


# Main Training Block
if __name__ == "__main__":
    with open('clozes', 'rb') as f:
        clozes_data = pickle.load(f)
    with open('vocab', 'rb') as f:
        vocab = pickle.load(f)

    # Launch Tensorflow Session
    print('Launching Tensorflow Session')
    with tf.Session() as sess:
        # Instantiate Model
        rnn_lm = RNNLangmod(len(vocab), FLAGS.embedding_size, FLAGS.num_steps,
                            FLAGS.hidden_size, FLAGS.batch_size,
                            FLAGS.learning_rate)

        # Initialize all Variables
        sess.run(tf.initialize_all_variables())

        # Start Training
        ex_bsz, bsz, steps = FLAGS.batch_size * \
            FLAGS.num_steps, FLAGS.batch_size, FLAGS.num_steps
        x, y = read_training()
        for epoch in range(FLAGS.num_epochs):
            # Preprocess and vectorize the data
            state, loss, iters, start_time = sess.run(
                rnn_lm.initial_state), 0., 0, time.time()

            for start, end in zip(range(0, len(x) - ex_bsz, ex_bsz),
                                  range(ex_bsz, len(x), ex_bsz)):

                # Build the Feed Dictionary, with inputs, outputs, dropout
                # probability, and states.
                feed_dict = {rnn_lm.X: x[start:end].reshape(bsz, steps),
                             rnn_lm.Y: y[start:end].reshape(bsz, steps),
                             rnn_lm.keep_prob: FLAGS.dropout_prob,
                             rnn_lm.initial_state[0]: state[0],
                             rnn_lm.initial_state[1]: state[1]}

                # Run the training operation with the Feed Dictionary,
                # fetch loss and update state.
                curr_loss, _, state = sess.run([
                    rnn_lm.loss_val, rnn_lm.train_op,
                    rnn_lm.final_state], feed_dict=feed_dict)
                # Update counters
                loss, iters = loss + curr_loss, iters + steps

                # Print Evaluation Statistics
                if start >= 20000:
                    break
                if start % FLAGS.eval_every == 0:
                    print('Epoch {} Words {}>{} Perplexity: {}. {} seconds'
                          .format(epoch, start, end, np.exp(loss / iters),
                                  time.time() - start_time))
                    loss, iters = 0.0, 0

        # Evaluate Test Perplexity
        test_loss, test_iters, total_correct, total_blanks = 0., 0, 0., 0
        d = {} # error test
        for i in range(NUM_CLOZES):
            x, y, choices, keys = read_cloze(i)
            state = sess.run(rnn_lm.initial_state)
            blank_i = 0
            for s, e in zip(range(0, len(x - ex_bsz), ex_bsz),
                            range(ex_bsz, len(x), ex_bsz)):
                # Build the Feed Dictionary, with inputs, outputs, dropout
                # probability, and states.
                feed_dict = {rnn_lm.X: x[s:e].reshape(bsz, steps),
                             rnn_lm.Y: y[s:e].reshape(bsz, steps),
                             rnn_lm.keep_prob: 1.0,
                             rnn_lm.initial_state[0]: state[0],
                             rnn_lm.initial_state[1]: state[1]}
                # Fetch the loss, and final state
                logits, curr_loss, state = sess.run([
                    rnn_lm.logits, rnn_lm.loss_val, rnn_lm.final_state],
                    feed_dict=feed_dict)
                for batch in range(bsz):
                    if y[s:e][batch] == vocab['BLANK']:
                        choices_d = {j: logits[batch][j]
                                     for j in range(len(logits[batch]))
                                     if j in choices[blank_i]}

                        d[(i,blank_i)] = {"logits": logits[batch],
                                          "choices": choices_d,
                                          "key": keys[blank_i],
                                          "correct": False}                                    
                        if choices_d[keys[blank_i]] == max(choices_d.values()):
                            total_correct += 1
                            d[(i,blank_i)]["correct"] = True
                        total_blanks += 1
                        blank_i += 1

                # Update counters
                test_loss += curr_loss
                test_iters += steps
        
        with open('error_analysis', 'wb') as f:
            pickle.dump(d, f)
        # Print Final Output
        print('Test Perplexity: {}'.format(np.exp(test_loss / test_iters)))
        print('Blank Accuracy: {}'.format(total_correct / total_blanks))
