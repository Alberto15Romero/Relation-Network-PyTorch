import torch
from src.utils import save_models, saving_path_rrn, get_answer, names_models
from sklearn.utils import shuffle
from collections import defaultdict
import random

def get_encoding(mlp, lstm, facts, question, device):

    h_q, h_f = lstm.reset_hidden_state(facts.size(0))

    question_emb, h_q = lstm.process_query(question, h_q)
    question_emb = question_emb.squeeze()[-1,:]

    facts_emb, h_f = lstm.process_facts(facts, h_f)
    facts_emb = facts_emb[:,-1,:]

    offset = random.randint(1,20)
    indexes = range(len(facts))

    onehot = torch.zeros(len(facts), 40, device=device)
    k=0
    for i in indexes:
        onehot[k, i+offset] = 1.
        k += 1

    input_mlp = torch.cat( (facts_emb, question_emb.repeat(len(facts), 1)), dim=1)
    input_mlp = torch.cat((input_mlp, onehot), dim=1)
    facts_encoded = mlp(input_mlp)

    return facts_encoded, question_emb, h_q, h_f

def train_single(train_stories, validation_stories, epochs, mlp, lstm, rrn, criterion, optimizer, print_every, no_save, device):

    avg_train_accuracies = []
    train_accuracies = []
    avg_train_losses = []
    train_losses = []

    val_accuracies = []
    val_losses = [1000.]
    best_val = val_losses[0]

    for i in range(epochs):

        for s in range(len(train_stories)):
            question, answer, facts, _ = train_stories[s]

            rrn.train()
            lstm.train()

            h = rrn.reset_g(1)

            facts_emb, question_emb, h_q, h_f = get_encoding(mlp, lstm, facts, question, device)
            hidden = facts_emb.clone()

            for reasoning_step in range(3):
                lstm.zero_grad()
                rrn.zero_grad()

                rr, hidden, h = rrn(facts_emb, hidden , h, question_emb)

                loss = criterion(rr.unsqueeze(0), answer)

                loss.backward()
                optimizer.step()


                if reasoning_step == 2:
                    correct, _ = get_answer(rr, answer)
                    train_accuracies.append(correct)
                    train_losses.append(loss.item())

            if ( ((s+1) %  print_every) == 0):
                print("Epoch ", i+1, ": ", s+1, " / ", len(train_stories))
                avg_train_losses.append(sum(train_losses)/len(train_losses))
                avg_train_accuracies.append(sum(train_accuracies)/len(train_accuracies))

                val_loss, val_accuracy = test(validation_stories,lstm,rrn,criterion)
                val_accuracies.append(val_accuracy)
                val_losses.append(val_loss)

                if not no_save:
                    if val_losses[-1] < best_val:
                        save_models([(lstm, names_models[0]), (rrn, names_models[2])], saving_path_rrn)
                        best_val = val_losses[-1]

                print("Train loss: ", avg_train_losses[-1], ". Validation loss: ", val_losses[-1])
                print("Train accuracy: ", avg_train_accuracies[-1], ". Validation accuracy: ", val_accuracies[-1])
                print()
                train_losses =  []
                train_accuracies = []

        train_stories = shuffle(train_stories)

    return avg_train_losses, avg_train_accuracies, val_losses[1:], val_accuracies

def test(stories, mlp, lstm, rrn, criterion, device):

    val_loss = 0.
    val_accuracy = 0.

    rrn.eval()
    lstm.eval()

    with torch.no_grad():

        for question, answer, facts, _ in stories: # for each story

            h = rrn.reset_g(1)

            facts_emb, question_emb, h_q, h_f = get_encoding(mlp, lstm, facts, question, device)
            hidden = facts_emb.clone()

            for reasoning_step in range(3):

                rr, hidden, h = rrn(facts_emb, hidden , h, question_emb)

                if reasoning_step==2:
                    loss = criterion(rr.unsqueeze(0), answer)
                    val_loss += loss.item()
                    correct, _ = get_answer(rr, answer)
                    val_accuracy += correct

        val_accuracy /= float(len(stories))
        val_loss /= float(len(stories))

        return val_loss, val_accuracy

def final_test(stories, mlp, lstm, rrn, criterion, device):

    val_loss = defaultdict(float)
    val_accuracy = defaultdict(float)

    rrn.eval()
    lstm.eval()

    with torch.no_grad():

        curr_task = stories[0][3]
        i = 0
        for question, answer, facts, task in stories: # for each story

            h = rrn.reset_g(1)

            facts_emb, question_emb, h_q, h_f = get_encoding(mlp, lstm, facts, question, device)
            hidden = facts_emb.clone()

            for reasoning_step in range(3):

                rr, hidden, h = rrn(facts_emb, hidden , h, question_emb)

                if reasoning_step==2:
                    loss = criterion(rr.unsqueeze(0), answer)
                    val_loss[task] += loss.item()
                    correct, _ = get_answer(rr, answer)
                    val_accuracy[task] += correct

            if curr_task != task:
                val_accuracy[curr_task] /= float(i)
                val_loss[curr_task] /= float(i)
                curr_task = task
                i=0


            i += 1

        val_accuracy[curr_task] /= float(i)
        val_loss[curr_task] /= float(i)

        return val_loss, val_accuracy