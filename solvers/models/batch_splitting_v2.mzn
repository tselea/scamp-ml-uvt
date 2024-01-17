int: n; % number of operations
int: W; % number of workstations

array[1..n, 1..W] of 0..1: I; % 1 if operation i ∈ workstation Y
int: M; % large positive number
int: movesize;
array[1..n, 1..W] of float: t; % processing time of operation i on workstation Y
array[1..n] of int: s; % the immediate downstream operation, or successor, of operation i
array[1..n] of int: b; % quantity of op i
array[1..n, 1..W] of float: K; % setuptime of op i on ws Y
int: E; % nr of final operations
array[1..E] of int: finalPosition; % ids of final operations
array[1..E] of float: D; % due date of final assembly

array[1..n, 1..W] of var 0..1: A; % A(Y,i) = 1 if operation i is assigned to workstation Y, 0 otherwise
array[1..n, 1..W] of var 0.0..M: S; % start time of operation i on ws Y
array[1..n, 1..W] of var 0.0..M: F; % completion time of operation i on ws Y
array[1..n, 1..W] of var 0..max(b): B; % batch size of operation i on ws Y


array[1..n] of -1.0..M: R;

constraint forall(i in 1..n)(sum(Y in 1..W where I[i,Y]=0)(A[i,Y]) = 0); % the task cannot be assigned to non-eligible workstations

%constraint forall(i in 1..n, Y1,Y2 in 1..W where Y1!=Y2 /\ s[i]!=-1 /\ A[i,Y1] = 1 /\ A[s[i],Y2] = 1)(S[s[i],Y2] >= S[i,Y1] + K[i,Y1] - K[s[i],Y2] + movesize * sum(y in 1..W)(A[s[i],y]) * t[i,Y1]); %(1)
%constraint forall(i in 1..n, Y1,Y2 in 1..W where Y1!=Y2 /\ s[i]!=-1 /\ A[i,Y1] = 1 /\ A[s[i],Y2] = 1)(F[s[i],Y2] >= F[i,Y1] + movesize * t[s[i],Y2]); %(2)
constraint forall(i in 1..n, Y1,Y2 in 1..W where s[i]!=-1 /\ A[i,Y1] = 1 /\ A[s[i],Y2] = 1)(S[s[i],Y2] >= F[i,Y1]); %(2)

constraint forall(i,j in 1..n, Y in 1..W where i!=j /\ A[i,Y] = 1 /\ A[j,Y] = 1)(F[i,Y] <= S[j,Y] \/ S[i,Y] >= F[j,Y]);
constraint forall(i in 1..n, Y in 1..W where A[i,Y] = 1)(F[i,Y] = S[i,Y] + K[i,Y] + B[i,Y]*t[i,Y]); %(4)
constraint forall(i in 1..n)(sum(Y in 1..W where A[i,Y]=1)(B[i,Y]) = b[i]); %5
constraint forall(i in 1..n, Y in 1..W where A[i,Y]=1)(B[i,Y] > 0);
constraint forall(i in 1..n, Y in 1..W where A[i,Y]=0)(B[i,Y] = 0 /\ S[i,Y] = 0 /\ F[i,Y] = 0); 

constraint forall(i in 1..n where R[i]!=-1, Y in 1..W where A[i,Y]=1)(S[i,Y] = R[i]);

constraint forall(z in 1..E, Y in 1..W where A[finalPosition[z],Y]=1)(F[finalPosition[z],Y] <= D[z]);

var float: objective;
constraint objective = max(z in 1..E, Y in 1..W where A[finalPosition[z],Y]=1)(F[finalPosition[z],Y]);
solve minimize objective;

%constraint objective = sum(i in 1..n, Y in 1..W)(S[i,Y]);
%solve maximize objective;


