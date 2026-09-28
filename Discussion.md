```If you need to see setup instructions or APi or more Please refer to README.md```
# Diagnostic Test Booking Application
The implemented Architecture is based on monolithic but as we have more scale and load we can go microservices based architecture. In this System we have maain services include User or Account , Centre, Test , Booking , Payment. Now if we look into it Our System mainly more ```read heavy``` System and there is less ```write request``` . As Creation of tests and Centre mainly done by Admin or if we introduce the multi-Seller System even then the read > write request. 
### Few Important Considerations:
1. We can handle if updates of new tests and centre will eventually update.
2. Payment shouldn't be taken twice 
3. System should be avaliable at any time and can handle read.

## Basic and essentials 
Now as we scale we need to go from monolithic to microservcies , so the basic to check first is that there is like CDN or edge server using cloudflare and other, in our case CDN cost might be low as we have very less images that we reuqire globally or major for all locations, but we gonna have images or might be video for user specify like there near location for that we can cache a local based images or video or particular location, Now after that we have or api gateway which redirect the request to the needed server and we can use loadbalancing as there might be multiple instance of it using any algorithm,(assuming using cloud services like AWS, AZURE ,GCP), On the databse the basic things we can do is connection caching  or using same connection string, As for our Case we can separate user,Payemnt ,Booking Db into separate and shards, On User we can create partations on USERID(We can discuss or can improve on more information or seeing tradeoff) and index for fast data gathering., Now as we know Centre is very less frequently chaning we can cache it but it cause major problem that is staleness we can solve this by our data pattern or we can do by applying TTl caching or other.

### 1. User creation and already existed problem
In our case we might not have so much user or daily user or load to tackel this problem we don't need to implement probability data strtucture, we can do this by simple hashmap in memeory and reduce db load.
### 2. Booking and payment
This is the main probem here :
1. When choosing a slot of time or test in centre multiple user do it we can came into race condition,(Assumed if we are looking in Time based and slot based system).
2. Payment and booking should be created and not allow multiple payment

For ```first``` we can use locking system we have multiple method but can simply do by using redis and but insure that it should expire we can define some time , we can discuss more what if that expire tag not work or some other condition then we need to dod this more complex by introducing a servcies
For ```second``` First we must use transactions it ensure atomicity and second on clicking a payment we must create a payment db with status pending and we can use its unique id as idemoptency key, which ensure multiple payment, when use click payment if it uses external servcie we can create a event in it with payment id as refernce and when payment is done we can register our webhook where we recieve when the payment status is done , so we can update it , but there is ```more  problems ``` that what if the external service notification system is crashed or not able to deliever or what happen when there is payment cut but no booking or need of refund

#### 1. External Service crash
When that occurs it cause problme we can solve this issue by introducing a automating cron or celery job process which reuqest the service or do pooling to ask for status for pending and change status according to it , but this also make this system more complex as we need to handle more thing, but in our case we need to assure that is working because in our case it just check for pending even it check for pending and it result to be true and cann't able to update it that is not be major problem compare to system where we might need this service external db and more complexity.
#### 2. Now Case of Payment refund.
This also cause complexity, in our case if load is low we might handle it by manual by just marking the payment refund as flag but if automatic system we need to introduce a whole layer like if payment is failed we can retry let say 3 time usign Queue system this ensure payment should be done , but not then we can according to our needs to can make different architecture and can introduce Dead letter queue where we can again retry to it just to store to manually work on it.

### TO Ensure our data stored
we can improve our system by introducing a messaging queue system and logs which is most necessary like wal which is most essentail when system crashs , when ever there is lot of request  or cretaion we can pass throught it this also ensure data not lost as it also work on log based, in our case we can partations this based on userid, can discuss this based on tradeoff and more.

### Using of Cloud or blob storage
let say we also provide a system where we can store large reports we can use blob storage like S3 bucket, google cloud storage,
if there are other group of people who might upload it we must ensure safty we  can use presigned or temporary url to add the file into system, i think these files might not be mcuh large , so we might not need chunking and all.

## Future scopes
1. Location can use lat,long we can use eucldian distance and find neary by centres, i dont think we need to do compexity of geo index or using grid based algos as there no real time,
2. Real time communication or chat with doctor - can be implemented but need different scopes and complexity
3. As for modern we might need ai chatbot or ai report reader - we need data to train on it and must ensure user data safety.

### NOTE : This is just first understanding and discussing , we can improve this on more itteration with discussing tradeoff and features needed , i might not have some concepts known for now but when searching and implementing looking for most optmial solution and discussion we can figure it out and solve problems. 